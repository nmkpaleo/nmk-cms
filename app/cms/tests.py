import copy
from datetime import timedelta
from decimal import Decimal
import json
import shutil
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone as django_timezone
from django.utils.timezone import now
from pathlib import Path

from cms.models import (
    Accession,
    AccessionNumberSeries,
    AccessionRow,
    Storage,
    InventoryStatus,
    Collection,
    Locality,
    Place,
    PlaceType,
    PlaceRelation,
    Preparation,
    PreparationStatus,
    UnexpectedSpecimen,
    DrawerRegister,
    Scanning,
    Media,
    Taxon,
    Reference,
    AccessionReference,
    FieldSlip,
    AccessionFieldSlip,
    Identification,
    NatureOfSpecimen,
    MediaQCLog,
    MediaQCComment,
    LLMUsageRecord,
    Element,
    Person,
)
from cms.utils import generate_accessions_from_series
from cms.forms import DrawerRegisterForm, AccessionNumberSeriesAdminForm
from cms.filters import DrawerRegisterFilter
from cms.resources import DrawerRegisterResource, PlaceResource
from tablib import Dataset
from cms.upload_processing import TIMESTAMP_FORMAT, process_file
from cms import scanning_utils
from cms.ocr_processing import (
    process_pending_scans,
    describe_accession_conflicts,
    UNKNOWN_FIELD_NUMBER_PREFIX,
    _apply_rows,
    MAX_OCR_ROWS_PER_ACCESSION,
)
from cms.qc import diff_media_payload


DEFAULT_USAGE_PAYLOAD = {
    "model": "gpt-4o",
    "request_id": "req-test",
    "prompt_tokens": 100,
    "completion_tokens": 200,
    "total_tokens": 300,
    "prompt_cost_usd": 0.0005,
    "completion_cost_usd": 0.003,
    "total_cost_usd": 0.0035,
}


def with_usage(payload: dict, *, usage_overrides: dict | None = None) -> dict:
    data = copy.deepcopy(payload)
    usage_payload = copy.deepcopy(DEFAULT_USAGE_PAYLOAD)
    if usage_overrides:
        usage_payload.update(usage_overrides)
    data["usage"] = usage_payload
    return data


class MediaQCDiffTests(TestCase):
    def test_diff_detects_reordered_rows_and_totals(self):
        original = {
            "accessions": [
                {
                    "rows": [
                        {
                            "_row_id": "row-0",
                            "specimen_suffix": {"interpreted": "A"},
                            "natures": [],
                        }
                    ],
                    "identifications": [
                        {"taxon": {"interpreted": "Pan"}},
                    ],
                    "references": [],
                    "field_slips": [],
                }
            ]
        }
        updated = {
            "accessions": [
                {
                    "rows": [
                        {
                            "_row_id": "row-1",
                            "specimen_suffix": {"interpreted": "B"},
                            "natures": [],
                        },
                        {
                            "_row_id": "row-0",
                            "specimen_suffix": {"interpreted": "A"},
                            "natures": [],
                        },
                    ],
                    "identifications": [
                        {"taxon": {"interpreted": "Pan"}},
                        {"taxon": {"interpreted": "Homo"}},
                    ],
                    "references": [
                        {
                            "reference_first_author": {"interpreted": "Doe"},
                            "reference_title": {"interpreted": "Sample"},
                            "reference_year": {"interpreted": 1999},
                            "page": {"interpreted": "10"},
                        }
                    ],
                    "field_slips": [],
                }
            ]
        }

        diff = diff_media_payload(original, updated)

        self.assertTrue(diff["rows_reordered"])
        totals = {entry["key"]: entry for entry in diff["count_diffs"]}
        self.assertEqual(totals["rows"]["original"], 1)
        self.assertEqual(totals["rows"]["current"], 2)
        self.assertEqual(totals["identifications"]["current"], 2)
        self.assertEqual(totals["references"]["current"], 1)

    def test_diff_warns_on_unlinked_identifications(self):
        original = {
            "accessions": [
                {
                    "rows": [
                        {"_row_id": "row-0", "specimen_suffix": {"interpreted": "A"}},
                        {"_row_id": "row-1", "specimen_suffix": {"interpreted": "B"}},
                    ],
                    "identifications": [
                        {"taxon": {"interpreted": "Pan"}},
                        {"taxon": {"interpreted": "Homo"}},
                    ],
                    "references": [],
                    "field_slips": [],
                }
            ]
        }
        updated = {
            "accessions": [
                {
                    "rows": [
                        {"_row_id": "row-0", "specimen_suffix": {"interpreted": "A"}},
                    ],
                    "identifications": [
                        {"taxon": {"interpreted": "Pan"}},
                    ],
                    "references": [],
                    "field_slips": [],
                }
            ]
        }

        diff = diff_media_payload(original, updated)
        warnings = {warning["code"] for warning in diff["warnings"]}
        self.assertIn("unlinked_identifications", warnings)


class DashboardQueueTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.intern_group = Group.objects.create(name="Interns")
        self.curator_group = Group.objects.create(name="Curators")
        self.collection_manager_group = Group.objects.create(name="Collection Managers")

        self.creator = self.User.objects.create_user(username="creator", password="pass")
        patcher = patch("cms.models.get_current_user", return_value=self.creator)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.media_pending_intern = Media.objects.create(
            file_name="pending-intern",
            qc_status=Media.QCStatus.PENDING_INTERN,
            ocr_status=Media.OCRStatus.COMPLETED,
            media_location="uploads/ocr/pending-intern.png",
        )
        self.media_pending_expert = Media.objects.create(
            file_name="pending-expert",
            qc_status=Media.QCStatus.PENDING_EXPERT,
        )
        self.media_returned = Media.objects.create(
            file_name="returned",
            qc_status=Media.QCStatus.REJECTED,
            rows_rearranged=True,
        )
        log = MediaQCLog.objects.create(
            media=self.media_returned,
            change_type=MediaQCLog.ChangeType.STATUS,
            field_name="qc_status",
            old_value={"qc_status": Media.QCStatus.PENDING_EXPERT},
            new_value={"qc_status": Media.QCStatus.REJECTED},
        )
        MediaQCComment.objects.create(log=log, comment="Needs fixes")

    def _create_user(self, username: str, groups: tuple[Group, ...] = ()):
        user = self.User.objects.create_user(username=username, password="pass")
        for group in groups:
            user.groups.add(group)
        return user

    def test_dashboard_sections_for_intern(self):
        user = self._create_user("intern", groups=(self.intern_group,))
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        sections = response.context["qc_sections"]
        labels = {section["label"] for section in sections}
        self.assertIn("Pending intern review", labels)
        self.assertIn("Returned for fixes", labels)
        self.assertNotIn("Needs expert attention", labels)
        returned_section = next(section for section in sections if section["key"] == "returned")
        self.assertEqual([media.pk for media in returned_section["entries"]], [self.media_returned.pk])
        self.assertEqual(response.context["qc_extra_links"], [])

    def test_dashboard_sections_for_expert(self):
        user = self._create_user("expert", groups=(self.curator_group,))
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        sections = response.context["qc_sections"]
        labels = {section["label"] for section in sections}
        self.assertIn("Pending intern review", labels)
        self.assertIn("Needs expert attention", labels)
        self.assertIn("Returned for fixes", labels)
        extra_labels = {extra["label"] for extra in response.context["qc_extra_links"]}
        self.assertIn("Media with rearranged rows", extra_labels)
        self.assertIn("Media with QC comments", extra_labels)

    def test_dashboard_for_user_without_role(self):
        user = self._create_user("visitor")
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["no_role"])
        self.assertEqual(response.context["qc_sections"], [])

    def test_rows_rearranged_requires_expert(self):
        user = self._create_user("intern-only", groups=(self.intern_group,))
        self.client.force_login(user)
        response = self.client.get(reverse("media_qc_rows_rearranged"))
        self.assertEqual(response.status_code, 403)

    def test_rows_rearranged_list_for_expert(self):
        user = self._create_user("manager", groups=(self.collection_manager_group,))
        self.client.force_login(user)
        response = self.client.get(reverse("media_qc_rows_rearranged"))
        self.assertContains(response, self.media_returned.file_name)

    def test_with_comments_queue_filters_correctly(self):
        user = self._create_user("manager-two", groups=(self.collection_manager_group,))
        self.client.force_login(user)
        response = self.client.get(reverse("media_qc_with_comments"))
        self.assertContains(response, self.media_returned.file_name)
        self.assertNotContains(response, self.media_pending_expert.file_name)

    def test_pending_intern_queue_access(self):
        intern_user = self._create_user("queue-intern", groups=(self.intern_group,))
        self.client.force_login(intern_user)
        response = self.client.get(reverse("media_qc_pending_intern"))
        self.assertContains(response, self.media_pending_intern.file_name)

    def test_pending_intern_queue_access_for_expert(self):
        expert_user = self._create_user("queue-expert", groups=(self.curator_group,))
        self.client.force_login(expert_user)
        response = self.client.get(reverse("media_qc_pending_intern"))
        self.assertContains(response, self.media_pending_intern.file_name)

    def test_pending_intern_queue_excludes_non_ocr_ready_media(self):
        Media.objects.create(
            file_name="pending-ocr-incomplete",
            qc_status=Media.QCStatus.PENDING_INTERN,
            ocr_status=Media.OCRStatus.PENDING,
            media_location="uploads/ocr/pending-ocr-incomplete.png",
        )
        Media.objects.create(
            file_name="pending-upload",
            qc_status=Media.QCStatus.PENDING_INTERN,
            ocr_status=Media.OCRStatus.COMPLETED,
            media_location="uploads/pending/pending-upload.png",
        )

        intern_user = self._create_user("queue-filter", groups=(self.intern_group,))
        self.client.force_login(intern_user)

        dashboard_response = self.client.get(reverse("dashboard"))
        sections = {section["key"]: section for section in dashboard_response.context["qc_sections"]}
        pending_entries = {media.file_name for media in sections["pending_intern"]["entries"]}

        self.assertIn(self.media_pending_intern.file_name, pending_entries)
        self.assertNotIn("pending-ocr-incomplete", pending_entries)
        self.assertNotIn("pending-upload", pending_entries)

        queue_response = self.client.get(reverse("media_qc_pending_intern"))
        self.assertContains(queue_response, self.media_pending_intern.file_name)
        self.assertNotContains(queue_response, "pending-ocr-incomplete")
        self.assertNotContains(queue_response, "pending-upload")

    def test_returned_queue_for_intern(self):
        intern_user = self._create_user("queue-returned", groups=(self.intern_group,))
        self.client.force_login(intern_user)
        response = self.client.get(reverse("media_qc_returned"))
        self.assertContains(response, self.media_returned.file_name)


class MediaNotificationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="notifier", password="pass")
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_transition_triggers_notification(self):
        media = Media.objects.create(
            file_name="notif",
            qc_status=Media.QCStatus.PENDING_INTERN,
            ocr_status=Media.OCRStatus.COMPLETED,
            media_location="uploads/ocr/notif.png",
        )
        with patch("cms.models.notify_media_qc_transition") as mock_notify:
            media.transition_qc(Media.QCStatus.PENDING_EXPERT, user=self.user, note="Ready")

        mock_notify.assert_called_once()
        args, kwargs = mock_notify.call_args
        self.assertEqual(args[0], media)
        self.assertEqual(args[1], Media.QCStatus.PENDING_INTERN)
        self.assertEqual(args[2], Media.QCStatus.PENDING_EXPERT)
        self.assertEqual(kwargs["user"], self.user)
        self.assertEqual(kwargs["note"], "Ready")

    def test_transition_same_status_skips_notification(self):
        media = Media.objects.create(
            file_name="notif-skip",
            qc_status=Media.QCStatus.PENDING_INTERN,
            ocr_status=Media.OCRStatus.COMPLETED,
            media_location="uploads/ocr/notif-skip.png",
        )
        with patch("cms.models.notify_media_qc_transition") as mock_notify:
            media.transition_qc(Media.QCStatus.PENDING_INTERN, user=self.user)

        mock_notify.assert_not_called()

class UploadProcessingTests(TestCase):
    """Tests for handling scan uploads using filename timestamps."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="intern", password="pass")
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.drawer = DrawerRegister.objects.create(
            code="DRW", description="Drawer", estimated_documents=1
        )
        start = scanning_utils.nairobi_now() - timedelta(minutes=5)
        end = start + timedelta(minutes=10)
        self.scanning = Scanning.objects.create(
            drawer=self.drawer, user=self.user, start_time=start, end_time=end
        )

    def tearDown(self):
        incoming_root = Path(settings.MEDIA_ROOT) / "uploads"
        if incoming_root.exists():
            import shutil

            shutil.rmtree(incoming_root)

    def _filename_for(self, dt: datetime) -> str:
        return dt.astimezone(scanning_utils.NAIROBI_TZ).strftime(
            f"{TIMESTAMP_FORMAT}.png"
        )

    def test_scanning_lookup_uses_filename_timestamp(self):
        incoming = Path(settings.MEDIA_ROOT) / "uploads" / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        filename = self._filename_for(self.scanning.start_time + timedelta(minutes=1))
        src = incoming / filename
        src.write_bytes(b"data")

        original_to_nairobi = scanning_utils.to_nairobi
        to_nairobi_calls = []

        def wrapped_to_nairobi(dt):
            to_nairobi_calls.append(dt)
            if len(to_nairobi_calls) == 1:
                self.assertFalse(django_timezone.is_naive(dt))
                self.assertEqual(dt.tzinfo, scanning_utils.NAIROBI_TZ)
            return original_to_nairobi(dt)

        with patch(
            "cms.scanning_utils.to_nairobi", side_effect=wrapped_to_nairobi
        ):
            process_file(src)

        self.assertGreaterEqual(len(to_nairobi_calls), 1)
        media = Media.objects.get(media_location=f"uploads/pending/{filename}")
        self.assertEqual(media.scanning, self.scanning)

    def test_upload_scan_restores_original_name_after_storage_collision(self):
        incoming = Path(settings.MEDIA_ROOT) / "uploads" / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        filename = self._filename_for(self.scanning.start_time + timedelta(minutes=2))
        original = incoming / filename
        original.write_bytes(b"original")

        self.user.is_staff = True
        self.user.save()

        upload = SimpleUploadedFile(filename, b"new-data", content_type="image/png")
        collision_name = f"{Path(filename).stem}_pNGQW5u.png"

        def fake_save(storage_self, name, content, max_length=None):
            saved_path = incoming / collision_name
            saved_path.write_bytes(b"uploaded")
            return collision_name

        processed_paths = []

        def fake_process(path):
            processed_paths.append(path)
            self.assertEqual(path.name, filename)
            self.assertTrue(path.exists())
            return path

        url = reverse("admin-upload-scan")
        self.client.force_login(self.user)

        with patch("cms.views.FileSystemStorage.save", new=fake_save):
            with patch("cms.views.process_file", side_effect=fake_process):
                response = self.client.post(url, {"files": [upload]}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(processed_paths), 1)
        self.assertTrue((incoming / filename).exists())
        self.assertFalse((incoming / collision_name).exists())


class GenerateAccessionsFromSeriesTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.series_user = User.objects.create_user(
            username="series_user", password="pass"
        )
        self.creator = User.objects.create_user(
            username="creator", password="pass"
        )

        # Patch get_current_user used in BaseModel to bypass authentication
        self.patcher = patch("cms.models.get_current_user", return_value=self.creator)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(
            abbreviation="COL", description="Test Collection"
        )
        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")
        self.series = AccessionNumberSeries.objects.create(
            user=self.series_user,
            start_from=1,
            end_at=10,
            current_number=1,
            is_active=True,
        )

    def test_generate_accessions_creates_records_and_increments_series(self):
        accessions = generate_accessions_from_series(
            self.series_user,
            count=3,
            collection=self.collection,
            specimen_prefix=self.locality,
            creator_user=self.creator,
        )

        self.series.refresh_from_db()
        self.assertEqual(self.series.current_number, 4)
        self.assertEqual(Accession.objects.count(), 3)
        numbers = list(Accession.objects.values_list("specimen_no", flat=True))
        self.assertEqual(numbers, [1, 2, 3])

        for acc in accessions:
            self.assertEqual(acc.collection, self.collection)
            self.assertEqual(acc.specimen_prefix, self.locality)
            self.assertEqual(acc.accessioned_by, self.series_user)

    def test_generate_accessions_raises_without_active_series(self):
        self.series.is_active = False
        self.series.save()

        with self.assertRaisesMessage(
            ValueError,
            f"No active accession number series found for user {self.series_user.username}.",
        ):
            generate_accessions_from_series(
                self.series_user,
                count=1,
                collection=self.collection,
                specimen_prefix=self.locality,
                creator_user=self.creator,
            )


class AccessionNumberSeriesAdminFormTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.tbi_user = User.objects.create_user(username="TBI", password="pass")
        self.shared_user = User.objects.create_user(username="shared", password="pass")
        self.other_shared_user = User.objects.create_user(username="shared2", password="pass")

    def test_form_exposes_widget_metadata_for_client_side(self):
        form = AccessionNumberSeriesAdminForm()

        widget_attrs = form.fields["user"].widget.attrs
        self.assertEqual(
            widget_attrs.get("data-dedicated-user-id"),
            str(self.tbi_user.pk),
        )

        series_map = json.loads(widget_attrs["data-series-starts"])
        self.assertEqual(series_map["tbi"], 1_000_000)
        self.assertEqual(series_map["shared"], 1)

    def test_tbi_series_uses_dedicated_pool(self):
        form = AccessionNumberSeriesAdminForm(data={
            "user": str(self.tbi_user.pk),
            "count": "5",
            "start_from": "",
            "current_number": "",
            "is_active": "True",
        })

        self.assertTrue(form.is_valid(), form.errors)

        series = form.save()
        self.assertEqual(series.user, self.tbi_user)
        self.assertEqual(series.start_from, 1_000_000)
        self.assertEqual(series.current_number, 1_000_000)
        self.assertEqual(series.end_at, 1_000_004)

    def test_tbi_series_advances_after_existing_range(self):
        AccessionNumberSeries.objects.create(
            user=self.tbi_user,
            start_from=1_000_000,
            end_at=1_000_009,
            current_number=1_000_005,
            is_active=False,
        )

        form = AccessionNumberSeriesAdminForm(data={
            "user": str(self.tbi_user.pk),
            "count": "3",
            "start_from": "",
            "current_number": "",
            "is_active": "True",
        })

        self.assertTrue(form.is_valid(), form.errors)

        series = form.save()
        self.assertEqual(series.start_from, 1_000_010)
        self.assertEqual(series.current_number, 1_000_010)
        self.assertEqual(series.end_at, 1_000_012)

    def test_shared_series_uses_shared_pool(self):
        AccessionNumberSeries.objects.create(
            user=self.shared_user,
            start_from=1,
            end_at=50,
            current_number=10,
            is_active=False,
        )

        form = AccessionNumberSeriesAdminForm(data={
            "user": str(self.other_shared_user.pk),
            "count": "10",
            "start_from": "",
            "current_number": "",
            "is_active": "True",
        })

        self.assertTrue(form.is_valid(), form.errors)

        series = form.save()
        self.assertEqual(series.start_from, 51)
        self.assertEqual(series.current_number, 51)
        self.assertEqual(series.end_at, 60)


class PreparationUpdateViewTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.preparator = User.objects.create_user(
            username="prep", password="pass"
        )
        self.curator = User.objects.create_user(
            username="cur", password="pass"
        )
        self.other_curator = User.objects.create_user(
            username="cur2", password="pass"
        )

        self.curators_group = Group.objects.create(name="Curators")
        self.preparators_group = Group.objects.create(name="Preparators")
        self.curators_group.user_set.add(self.curator, self.other_curator)
        self.preparators_group.user_set.add(self.preparator)

        self.patcher = patch("cms.models.get_current_user", return_value=self.curator)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(
            abbreviation="COL", description="Test Collection"
        )
        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")
        self.accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
            accessioned_by=self.preparator,
        )
        self.accession_row = AccessionRow.objects.create(accession=self.accession)
        self.preparation = Preparation.objects.create(
            accession_row=self.accession_row,
            preparator=self.preparator,
            curator=self.curator,
            preparation_type="cleaning",
            started_on="2023-01-01",
            status=PreparationStatus.COMPLETED,
        )

    def test_curator_must_match_to_edit(self):
        self.client.login(username="cur2", password="pass")
        url = reverse("preparation_edit", args=[self.preparation.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_curator_sees_only_approved_declined_choices(self):
        self.client.login(username="cur", password="pass")
        url = reverse("preparation_edit", args=[self.preparation.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        choices = [c[0] for c in response.context["form"].fields["status"].choices]
        self.assertEqual(
            choices,
            [PreparationStatus.APPROVED, PreparationStatus.DECLINED],
        )

    def test_curator_cannot_set_invalid_status(self):
        self.client.login(username="cur", password="pass")
        url = reverse("preparation_edit", args=[self.preparation.pk])
        data = {
            "accession_row": self.accession_row.pk,
            "preparation_type": "cleaning",
            "preparator": self.preparator.pk,
            "started_on": "2023-01-01",
            "status": PreparationStatus.IN_PROGRESS,
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response,
            "form",
            "status",
            "You can only set status to Approved or Declined.",
        )


class PreparationDetailViewTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.preparator = User.objects.create_user(
            username="prep", password="pass"
        )
        self.curator = User.objects.create_user(
            username="cur", password="pass"
        )
        self.other_curator = User.objects.create_user(
            username="cur2", password="pass"
        )

        self.curators_group = Group.objects.create(name="Curators")
        self.preparators_group = Group.objects.create(name="Preparators")
        self.curators_group.user_set.add(self.curator, self.other_curator)
        self.preparators_group.user_set.add(self.preparator)

        self.patcher = patch("cms.models.get_current_user", return_value=self.curator)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(
            abbreviation="COL", description="Test Collection"
        )
        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")
        self.accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
            accessioned_by=self.preparator,
        )
        self.accession_row = AccessionRow.objects.create(accession=self.accession)
        self.preparation = Preparation.objects.create(
            accession_row=self.accession_row,
            preparator=self.preparator,
            curator=self.curator,
            preparation_type="cleaning",
            started_on="2023-01-01",
            status=PreparationStatus.IN_PROGRESS,
        )

    def test_preparator_sees_edit_button(self):
        self.client.login(username="prep", password="pass")
        url = reverse("preparation_detail", args=[self.preparation.pk])
        response = self.client.get(url)
        self.assertContains(response, "Edit Preparation")

    def test_assigned_curator_sees_edit_button(self):
        self.client.login(username="cur", password="pass")
        url = reverse("preparation_detail", args=[self.preparation.pk])
        response = self.client.get(url)
        self.assertContains(response, "Edit Preparation")

    def test_unassigned_curator_does_not_see_edit_button(self):
        self.client.login(username="cur2", password="pass")
        url = reverse("preparation_detail", args=[self.preparation.pk])
        response = self.client.get(url)
        self.assertNotContains(response, "Edit Preparation")


class DashboardViewCuratorTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.preparator = User.objects.create_user(
            username="prep", password="pass"
        )
        self.curator = User.objects.create_user(
            username="cur", password="pass"
        )
        self.other_curator = User.objects.create_user(
            username="cur2", password="pass"
        )

        self.curators_group = Group.objects.create(name="Curators")
        self.preparators_group = Group.objects.create(name="Preparators")
        self.curators_group.user_set.add(self.curator, self.other_curator)
        self.preparators_group.user_set.add(self.preparator)

        self.patcher = patch("cms.models.get_current_user", return_value=self.curator)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(
            abbreviation="COL", description="Test Collection"
        )
        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")
        self.accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
            accessioned_by=self.preparator,
        )
        self.accession_row1 = AccessionRow.objects.create(
            accession=self.accession, specimen_suffix="A"
        )
        self.accession_row2 = AccessionRow.objects.create(
            accession=self.accession, specimen_suffix="B"
        )

        self.curator_prep = Preparation.objects.create(
            accession_row=self.accession_row1,
            preparator=self.preparator,
            curator=self.curator,
            preparation_type="cleaning",
            started_on="2023-01-01",
            status=PreparationStatus.COMPLETED,
        )
        self.other_curator_prep = Preparation.objects.create(
            accession_row=self.accession_row2,
            preparator=self.preparator,
            curator=self.other_curator,
            preparation_type="cleaning",
            started_on="2023-01-01",
            status=PreparationStatus.COMPLETED,
        )

    def test_curator_sees_only_their_completed_preparations(self):
        self.client.login(username="cur", password="pass")
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["completed_preparations"]),
            [self.curator_prep],
        )


class DashboardViewCollectionManagerTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.manager = User.objects.create_user(
            username="cm", password="pass"
        )
        self.other_manager = User.objects.create_user(
            username="cm2", password="pass"
        )

        self.group = Group.objects.create(name="Collection Managers")
        self.group.user_set.add(self.manager, self.other_manager)

        self.patcher = patch("cms.models.get_current_user", return_value=self.manager)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(
            abbreviation="COL", description="Test Collection"
        )
        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")

        AccessionNumberSeries.objects.create(
            user=self.manager,
            start_from=1,
            end_at=100,
            current_number=1,
            is_active=True,
        )

        self.unassigned = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
            accessioned_by=self.manager,
        )
        self.assigned = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=2,
            accessioned_by=self.manager,
        )
        AccessionRow.objects.create(accession=self.assigned)

        for i in range(3, 14):
            Accession.objects.create(
                collection=self.collection,
                specimen_prefix=self.locality,
                specimen_no=i,
                accessioned_by=self.manager,
            )

        with patch("cms.models.get_current_user", return_value=self.other_manager):
            self.row_accession = Accession.objects.create(
                collection=self.collection,
                specimen_prefix=self.locality,
                specimen_no=99,
                accessioned_by=self.other_manager,
            )

        AccessionRow.objects.create(accession=self.row_accession)

        self.client.login(username="cm", password="pass")

    def test_collection_manager_dashboard_lists(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_collection_manager"])
        self.assertTrue(response.context["has_active_series"])
        self.assertEqual(len(response.context["unassigned_accessions"]), 10)
        self.assertNotIn(self.assigned, response.context["unassigned_accessions"])
        self.assertEqual(len(response.context["latest_accessions"]), 10)
        self.assertIn(self.row_accession, response.context["latest_accessions"])

    def test_dashboard_lists_quality_control_media_for_expert(self):
        now_time = now()
        media_items = []
        for idx in range(11):
            media = Media.objects.create(
                media_location=f"uploads/expert/sample-{idx}.jpg",
                file_name=f"Expert Sample {idx}",
                qc_status=Media.QCStatus.PENDING_EXPERT,
            )
            Media.objects.filter(pk=media.pk).update(
                modified_on=now_time - timedelta(minutes=idx)
            )
            media_items.append(media)

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Quality Control")
        self.assertContains(response, Media.QCStatus.PENDING_EXPERT.label)
        self.assertContains(response, media_items[0].file_name)
        self.assertNotContains(response, media_items[10].file_name)
        self.assertContains(
            response, reverse("media_expert_qc", args=[media_items[0].uuid])
        )

    def test_collection_manager_without_active_series(self):
        AccessionNumberSeries.objects.filter(user=self.manager).update(is_active=False)
        response = self.client.get(reverse("dashboard"))
        self.assertFalse(response.context["has_active_series"])


class DashboardViewPreparatorTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(username="prep", password="pass")

        self.group = Group.objects.create(name="Preparators")
        self.group.user_set.add(self.user)

        self.patcher = patch("cms.models.get_current_user", return_value=self.user)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(
            abbreviation="COL", description="Test Collection"
        )
        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")

        for i in range(15):
            accession = Accession.objects.create(
                collection=self.collection,
                specimen_prefix=self.locality,
                specimen_no=i,
                accessioned_by=self.user,
            )
            row = AccessionRow.objects.create(accession=accession)
            Preparation.objects.create(
                accession_row=row,
                preparator=self.user,
                preparation_type="cleaning",
                started_on="2023-01-01",
                status=PreparationStatus.IN_PROGRESS,
            )

        self.client.login(username="prep", password="pass")

    def test_preparator_dashboard_lists_limited(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["my_preparations"]), 10)
        self.assertEqual(len(response.context["priority_tasks"]), 10)


class DashboardViewMultipleRolesTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(username="multi", password="pass")

        self.prep_group = Group.objects.create(name="Preparators")
        self.cm_group = Group.objects.create(name="Collection Managers")
        self.prep_group.user_set.add(self.user)
        self.cm_group.user_set.add(self.user)

        self.patcher = patch("cms.models.get_current_user", return_value=self.user)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(
            abbreviation="COL", description="Test Collection"
        )
        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")

        AccessionNumberSeries.objects.create(
            user=self.user,
            start_from=1,
            end_at=100,
            current_number=1,
            is_active=True,
        )

        self.unassigned = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
            accessioned_by=self.user,
        )

        self.prep_accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=2,
            accessioned_by=self.user,
        )
        self.accession_row = AccessionRow.objects.create(accession=self.prep_accession)
        self.preparation = Preparation.objects.create(
            accession_row=self.accession_row,
            preparator=self.user,
            preparation_type="cleaning",
            started_on="2023-01-01",
            status=PreparationStatus.IN_PROGRESS,
        )

        self.client.login(username="multi", password="pass")

    def test_dashboard_shows_all_role_sections(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_preparator"])
        self.assertTrue(response.context["is_collection_manager"])
        self.assertIn(self.preparation, response.context["my_preparations"])
        self.assertIn(self.unassigned, response.context["unassigned_accessions"])


class UnexpectedSpecimenLoggingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="tester", password="pass")

        self.patcher = patch("cms.models.get_current_user", return_value=self.user)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_logging_creates_record(self):
        self.client.login(username="tester", password="pass")
        response = self.client.post(reverse("inventory_log_unexpected"), {"identifier": "XYZ"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            UnexpectedSpecimen.history.filter(identifier="XYZ").exists()
        )


class DrawerRegisterTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="cm", password="pass")

        self.patcher = patch("cms.models.get_current_user", return_value=self.user)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_requires_user_when_in_progress(self):
        form = DrawerRegisterForm(
            data={
                "code": "ABC",
                "description": "Test",
                "estimated_documents": 5,
                "scanning_status": DrawerRegister.ScanningStatus.IN_PROGRESS,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Scanning user is required", form.non_field_errors()[0])

    def test_taxa_field_limited_to_orders(self):
        order_taxon = Taxon.objects.create(
            taxon_rank="Order",
            taxon_name="Ordertaxon",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="Ordertaxon",
            family="",
            genus="",
            species="",
        )
        Taxon.objects.create(
            taxon_rank="Family",
            taxon_name="Familytaxon",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="o",
            family="Familytaxon",
            genus="g",
            species="s",
        )
        form = DrawerRegisterForm()
        self.assertEqual(list(form.fields["taxa"].queryset), [order_taxon])

    def test_edit_form_includes_existing_taxa(self):
        order_taxon = Taxon.objects.create(
            taxon_rank="Order",
            taxon_name="Ordertaxon",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="Ordertaxon",
            family="",
            genus="",
            species="",
        )
        family_taxon = Taxon.objects.create(
            taxon_rank="Family",
            taxon_name="Familytaxon",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="o",
            family="Familytaxon",
            genus="g",
            species="s",
        )
        drawer = DrawerRegister.objects.create(
            code="ABC",
            description="Drawer",
            estimated_documents=1,
        )
        drawer.taxa.add(family_taxon)
        form = DrawerRegisterForm(instance=drawer)
        self.assertEqual(set(form.fields["taxa"].queryset), {order_taxon, family_taxon})

    def test_filter_taxa_field_limited_to_orders(self):
        order_taxon = Taxon.objects.create(
            taxon_rank="Order",
            taxon_name="Ordertaxon",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="Ordertaxon",
            family="",
            genus="",
            species="",
        )
        Taxon.objects.create(
            taxon_rank="Family",
            taxon_name="Familytaxon",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="o",
            family="Familytaxon",
            genus="g",
            species="s",
        )
        f = DrawerRegisterFilter({}, queryset=DrawerRegister.objects.all())
        self.assertEqual(list(f.form.fields["taxa"].queryset), [order_taxon])

    def test_filter_by_code_and_status(self):
        DrawerRegister.objects.create(
            code="ABC", description="Drawer A", estimated_documents=1
        )
        DrawerRegister.objects.create(
            code="XYZ",
            description="Drawer B",
            estimated_documents=2,
            scanning_status=DrawerRegister.ScanningStatus.SCANNED,
        )

        f = DrawerRegisterFilter({"code": "ABC"}, queryset=DrawerRegister.objects.all())
        self.assertEqual(list(f.qs.values_list("code", flat=True)), ["ABC"])
        f = DrawerRegisterFilter({"scanning_status": DrawerRegister.ScanningStatus.SCANNED}, queryset=DrawerRegister.objects.all())
        self.assertEqual(list(f.qs.values_list("code", flat=True)), ["XYZ"])

    def test_order_taxon_str_falls_back_to_name(self):
        taxon = Taxon.objects.create(
            taxon_rank="Order",
            taxon_name="Coleoptera",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="Coleoptera",
            family="",
            genus="",
            species="",
        )
        self.assertEqual(str(taxon), "Coleoptera")

    def test_drawer_register_resource_roundtrip(self):
        loc1 = Locality.objects.create(abbreviation="L1", name="Loc1")
        loc2 = Locality.objects.create(abbreviation="L2", name="Loc2")
        taxon1 = Taxon.objects.create(
            taxon_rank="Order",
            taxon_name="Order1",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="Order1",
            family="",
            genus="",
            species="",
        )
        taxon2 = Taxon.objects.create(
            taxon_rank="Order",
            taxon_name="Order2",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="Order2",
            family="",
            genus="",
            species="",
        )
        user1 = get_user_model().objects.create_user(username="u1")
        user2 = get_user_model().objects.create_user(username="u2")
        drawer = DrawerRegister.objects.create(
            code="ABC",
            description="Desc",
            estimated_documents=5,
            scanning_status=DrawerRegister.ScanningStatus.IN_PROGRESS,
        )
        drawer.localities.set([loc1, loc2])
        drawer.taxa.set([taxon1, taxon2])
        drawer.scanning_users.set([user1, user2])

        resource = DrawerRegisterResource()
        dataset = resource.export()
        DrawerRegister.objects.all().delete()
        result = resource.import_data(dataset, dry_run=False)
        self.assertFalse(result.has_errors())
        imported = DrawerRegister.objects.get(code="ABC")
        self.assertQuerysetEqual(
            imported.localities.order_by("id"), [loc1, loc2], transform=lambda x: x
        )
        self.assertQuerysetEqual(
            imported.taxa.order_by("id"), [taxon1, taxon2], transform=lambda x: x
        )
        self.assertQuerysetEqual(
            imported.scanning_users.order_by("id"), [user1, user2], transform=lambda x: x
        )

    def test_resource_imports_semicolon_values_with_spaces(self):
        loc1 = Locality.objects.create(abbreviation="L1", name="Loc1")
        loc2 = Locality.objects.create(abbreviation="L2", name="Loc2")
        taxon1 = Taxon.objects.create(
            taxon_rank="Order",
            taxon_name="Order1",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="Order1",
            family="",
            genus="",
            species="",
        )
        taxon2 = Taxon.objects.create(
            taxon_rank="Order",
            taxon_name="Order2",
            kingdom="k",
            phylum="p",
            class_name="c",
            order="Order2",
            family="",
            genus="",
            species="",
        )
        user1 = get_user_model().objects.create_user(username="u1")
        user2 = get_user_model().objects.create_user(username="u2")

        dataset = Dataset(
            headers=[
                "code",
                "description",
                "localities",
                "taxa",
                "estimated_documents",
                "scanning_status",
                "scanning_users",
            ]
        )
        dataset.append(
            [
                "XYZ",
                "Desc",
                f"{loc1.name}; {loc2.name}",
                f"{taxon1.taxon_name}; {taxon2.taxon_name}",
                5,
                DrawerRegister.ScanningStatus.IN_PROGRESS,
                f"{user1.username}; {user2.username}",
            ]
        )

        resource = DrawerRegisterResource()
        result = resource.import_data(dataset, dry_run=False)
        self.assertFalse(result.has_errors())
        drawer = DrawerRegister.objects.get(code="XYZ")
        self.assertQuerysetEqual(
            drawer.localities.order_by("id"), [loc1, loc2], transform=lambda x: x
        )
        self.assertQuerysetEqual(
            drawer.taxa.order_by("id"), [taxon1, taxon2], transform=lambda x: x
        )
        self.assertQuerysetEqual(
            drawer.scanning_users.order_by("id"), [user1, user2], transform=lambda x: x
        )


class ScanningTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="intern", password="pass")
        group = Group.objects.create(name="Interns")
        self.user.groups.add(group)
        self.patcher = patch("cms.models.get_current_user", return_value=self.user)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.drawer = DrawerRegister.objects.create(
            code="ABC", description="Drawer", estimated_documents=1,
            scanning_status=DrawerRegister.ScanningStatus.IN_PROGRESS,
        )
        self.drawer.scanning_users.add(self.user)

    def test_dashboard_lists_drawers_for_intern(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "ABC")
        self.assertContains(response, "Drawer")
        self.assertContains(response, "Start scanning task")
        self.assertContains(response, "Stop scanning task")

    def test_dashboard_lists_quality_control_media_for_intern(self):
        now_time = now()
        pending_media = []
        for idx in range(11):
            media = Media.objects.create(
                media_location=f"uploads/ocr/sample-{idx}.jpg",
                file_name=f"Pending Sample {idx}",
                qc_status=Media.QCStatus.PENDING_INTERN,
                ocr_status=Media.OCRStatus.COMPLETED,
            )
            Media.objects.filter(pk=media.pk).update(
                modified_on=now_time - timedelta(minutes=idx)
            )
            pending_media.append(media)

        latest_pending = pending_media[0]
        rejected_media = Media.objects.create(
            media_location="uploads/rejected/sample.jpg",
            file_name="Rejected Sample",
            qc_status=Media.QCStatus.REJECTED,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Quality Control")
        self.assertContains(response, "Pending Intern Review")
        self.assertContains(response, "Rejected")
        self.assertContains(response, "Pending Sample 0")
        self.assertContains(response, "Pending Sample 9")
        self.assertNotContains(response, "Pending Sample 10")
        self.assertContains(
            response, reverse("media_intern_qc", args=[latest_pending.uuid])
        )
        self.assertContains(
            response, reverse("media_intern_qc", args=[rejected_media.uuid])
        )

    def test_start_and_stop_scan(self):
        self.client.force_login(self.user)
        self.client.post(reverse("drawer_start_scan", args=[self.drawer.id]))
        scan = Scanning.objects.get()
        self.assertIsNotNone(scan.start_time)
        self.assertIsNone(scan.end_time)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, scan.start_time.strftime("%Y-%m-%d"))
        self.assertContains(response, "scan-timer")
        self.client.post(reverse("drawer_stop_scan", args=[self.drawer.id]))
        scan.refresh_from_db()
        self.assertIsNotNone(scan.end_time)

    def test_scan_auto_completes_after_eight_hours(self):
        start = datetime(2024, 1, 1, 8, 0, tzinfo=ZoneInfo("Africa/Nairobi"))
        scan = Scanning.objects.create(
            drawer=self.drawer,
            user=self.user,
            start_time=start,
        )
        self.client.force_login(self.user)
        with patch("cms.scanning_utils.nairobi_now", return_value=start + timedelta(hours=9)):
            self.client.get(reverse("dashboard"))
        scan.refresh_from_db()
        expected_end = scanning_utils.calculate_scan_auto_end(start)
        self.assertEqual(
            scanning_utils.to_nairobi(scan.end_time),
            expected_end,
        )

    def test_scan_auto_completes_at_midnight(self):
        start = datetime(2024, 1, 1, 21, 0, tzinfo=ZoneInfo("Africa/Nairobi"))
        scan = Scanning.objects.create(
            drawer=self.drawer,
            user=self.user,
            start_time=start,
        )
        self.client.force_login(self.user)
        with patch("cms.scanning_utils.nairobi_now", return_value=start + timedelta(hours=5)):
            self.client.get(reverse("dashboard"))
        scan.refresh_from_db()
        expected_end = scanning_utils.calculate_scan_auto_end(start)
        self.assertEqual(
            scanning_utils.to_nairobi(scan.end_time),
            expected_end,
        )

    def test_dashboard_limits_my_drawers_to_one(self):
        other_drawer = DrawerRegister.objects.create(
            code="XYZ",
            description="Other",
            estimated_documents=1,
            scanning_status=DrawerRegister.ScanningStatus.IN_PROGRESS,
            priority=10,
        )
        other_drawer.scanning_users.add(self.user)
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))
        drawers = response.context["my_drawers"]
        self.assertEqual(len(drawers), 1)
        self.assertEqual(drawers[0].code, "XYZ")

    def test_drawer_detail_shows_scans(self):
        Scanning.objects.create(
            drawer=self.drawer,
            user=self.user,
            start_time=now(),
            end_time=now(),
        )
        admin = get_user_model().objects.create_superuser("admin", "admin@example.com", "pass")
        self.client.force_login(admin)
        response = self.client.get(reverse("drawerregister_detail", args=[self.drawer.id]))
        self.assertContains(response, self.user.username)


class AccessionVisibilityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.creator = User.objects.create_user(username="creator", password="pass")
        self.cm_user = User.objects.create_user(username="cm", password="pass")
        self.cm_group = Group.objects.create(name="Collection Managers")
        self.cm_group.user_set.add(self.cm_user)

        self.patcher = patch("cms.models.get_current_user", return_value=self.creator)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(abbreviation="COL", description="Test")
        self.locality = Locality.objects.create(abbreviation="LC", name="Loc")

        self.published_accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
        )
        self.unpublished_accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=2,
        )
        Accession.objects.filter(pk=self.published_accession.pk).update(is_published=True)
        Accession.objects.filter(pk=self.unpublished_accession.pk).update(is_published=False)
        self.published_accession.refresh_from_db()
        self.unpublished_accession.refresh_from_db()

    def test_locality_detail_hides_unpublished_for_public(self):
        url = reverse("locality_detail", args=[self.locality.pk])
        response = self.client.get(url)
        self.assertContains(response, str(self.published_accession.specimen_no))
        self.assertNotIn(
            f"/accessions/{self.unpublished_accession.pk}/",
            response.content.decode(),
        )

    def test_locality_detail_shows_unpublished_for_collection_manager(self):
        self.client.login(username="cm", password="pass")
        url = reverse("locality_detail", args=[self.locality.pk])
        response = self.client.get(url)
        self.assertContains(response, str(self.unpublished_accession.specimen_no))

    def test_accession_detail_unpublished_returns_404_for_public(self):
        url = reverse("accession_detail", args=[self.unpublished_accession.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_accession_detail_unpublished_allowed_for_collection_manager(self):
        self.client.login(username="cm", password="pass")
        url = reverse("accession_detail", args=[self.unpublished_accession.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class ReferenceListViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.creator = User.objects.create_user(username="creator", password="pass")
        self.collection_manager = User.objects.create_user(username="manager", password="pass")
        self.cm_group = Group.objects.create(name="Collection Managers")
        self.cm_group.user_set.add(self.collection_manager)

        self.patcher = patch("cms.models.get_current_user", return_value=self.creator)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(
            abbreviation="COL",
            description="Collection",
        )
        self.locality = Locality.objects.create(abbreviation="LOC", name="Locality")

        self.reference_with_published = Reference.objects.create(
            title="Published Reference",
            first_author="Author Published",
            year="2001",
            citation="Citation Published",
        )
        self.reference_with_unpublished = Reference.objects.create(
            title="Unpublished Reference",
            first_author="Author Unpublished",
            year="2002",
            citation="Citation Unpublished",
        )
        self.reference_without_accessions = Reference.objects.create(
            title="Orphan Reference",
            first_author="Author Orphan",
            year="2003",
            citation="Citation Orphan",
        )

        self.published_accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
        )
        self.unpublished_accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=2,
        )
        self.second_published_accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=3,
        )

        AccessionReference.objects.create(
            accession=self.published_accession,
            reference=self.reference_with_published,
        )
        AccessionReference.objects.create(
            accession=self.unpublished_accession,
            reference=self.reference_with_unpublished,
        )
        AccessionReference.objects.create(
            accession=self.second_published_accession,
            reference=self.reference_with_published,
        )

        self.published_accession.refresh_from_db()
        self.unpublished_accession.refresh_from_db()
        self.second_published_accession.refresh_from_db()

        Accession.objects.filter(pk=self.unpublished_accession.pk).update(is_published=False)
        self.unpublished_accession.refresh_from_db()

    def test_public_user_sees_only_references_with_published_accessions(self):
        response = self.client.get(reverse("reference_list"))
        self.assertEqual(response.status_code, 200)

        page = response.context["page_obj"]
        self.assertEqual(
            [reference.pk for reference in page.object_list],
            [self.reference_with_published.pk],
        )
        self.assertEqual(page.object_list[0].accession_count, 2)

        self.assertContains(
            response,
            '<a href="?sort=accessions&amp;direction=asc"',
        )
        self.assertContains(response, self.reference_with_published.first_author)
        self.assertNotContains(response, self.reference_with_unpublished.first_author)
        self.assertNotContains(response, self.reference_without_accessions.first_author)

    def test_collection_manager_sees_all_references_with_accession_counts(self):
        self.client.login(username="manager", password="pass")
        response = self.client.get(reverse("reference_list"))
        self.assertEqual(response.status_code, 200)

        page = response.context["page_obj"]
        self.assertCountEqual(
            [reference.pk for reference in page.object_list],
            [
                self.reference_with_published.pk,
                self.reference_with_unpublished.pk,
                self.reference_without_accessions.pk,
            ],
        )

        accession_counts = {
            reference.pk: reference.accession_count for reference in page.object_list
        }
        self.assertEqual(accession_counts[self.reference_with_published.pk], 2)
        self.assertEqual(accession_counts[self.reference_with_unpublished.pk], 1)
        self.assertEqual(accession_counts[self.reference_without_accessions.pk], 0)

    def test_collection_manager_can_sort_by_accession_count(self):
        self.client.login(username="manager", password="pass")

        response = self.client.get(
            reverse("reference_list"), {"sort": "accessions", "direction": "desc"}
        )
        self.assertEqual(response.status_code, 200)

        page = response.context["page_obj"]
        self.assertEqual(
            [reference.pk for reference in page.object_list],
            [
                self.reference_with_published.pk,
                self.reference_with_unpublished.pk,
                self.reference_without_accessions.pk,
            ],
        )
        self.assertEqual(response.context["current_sort"], "accessions")
        self.assertEqual(response.context["current_direction"], "desc")
        self.assertEqual(response.context["sort_directions"]["accessions"], "asc")

        response = self.client.get(
            reverse("reference_list"), {"sort": "accessions", "direction": "asc"}
        )

        page = response.context["page_obj"]
        self.assertEqual(
            [reference.pk for reference in page.object_list],
            [
                self.reference_without_accessions.pk,
                self.reference_with_unpublished.pk,
                self.reference_with_published.pk,
            ],
        )

class PlaceModelTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="user", password="pass")
        self.patcher = patch("cms.models.get_current_user", return_value=self.user)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")

    def test_hierarchy_and_validation(self):
        region = Place.objects.create(
            locality=self.locality,
            name="Region",
            place_type=PlaceType.REGION,
        )
        self.assertEqual(region.part_of_hierarchy, "Region")

        site = Place.objects.create(
            locality=self.locality,
            name="Site",
            place_type=PlaceType.SITE,
            related_place=region,
            relation_type=PlaceRelation.PART_OF,
        )
        self.assertEqual(site.part_of_hierarchy, "Region | Site")

        synonym = Place.objects.create(
            locality=self.locality,
            name="R",
            place_type=PlaceType.REGION,
            related_place=region,
            relation_type=PlaceRelation.SYNONYM,
        )
        self.assertEqual(synonym.part_of_hierarchy, region.part_of_hierarchy)

        invalid = Place(
            locality=self.locality,
            name="Invalid",
            place_type=PlaceType.SITE,
            related_place=region,
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_related_place_must_share_locality(self):
        other_locality = Locality.objects.create(abbreviation="OT", name="Other")
        region = Place.objects.create(
            locality=other_locality,
            name="OtherRegion",
            place_type=PlaceType.REGION,
        )
        invalid = Place(
            locality=self.locality,
            name="Site",
            place_type=PlaceType.SITE,
            related_place=region,
            relation_type=PlaceRelation.PART_OF,
        )
        with self.assertRaisesMessage(ValidationError, "Related place must belong to the same locality."):
            invalid.full_clean()

    def test_prevent_circular_part_of(self):
        parent = Place.objects.create(
            locality=self.locality,
            name="Region",
            place_type=PlaceType.REGION,
        )
        child = Place.objects.create(
            locality=self.locality,
            name="Site",
            place_type=PlaceType.SITE,
            related_place=parent,
            relation_type=PlaceRelation.PART_OF,
        )
        parent.related_place = child
        parent.relation_type = PlaceRelation.PART_OF
        with self.assertRaisesMessage(ValidationError, "Cannot set a higher-level place as part of its descendant."):
            parent.full_clean()


class PlaceViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="viewer", password="pass")

        self.patcher = patch("cms.models.get_current_user", return_value=self.user)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")
        self.place = Place.objects.create(
            locality=self.locality,
            name="Region",
            place_type=PlaceType.REGION,
        )

    def test_place_list_view(self):
        response = self.client.get(reverse('place_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Region")

    def test_place_detail_view(self):
        response = self.client.get(reverse('place_detail', args=[self.place.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Higher Geography")
        self.assertContains(response, self.place.part_of_hierarchy)

    def test_place_detail_view_lists_lower_geography(self):
        child = Place.objects.create(
            locality=self.locality,
            name="Site",
            place_type=PlaceType.SITE,
            related_place=self.place,
            relation_type=PlaceRelation.PART_OF,
        )
        response = self.client.get(reverse('place_detail', args=[self.place.pk]))
        self.assertContains(response, "Lower Geography")
        self.assertContains(response, child.name)

    def test_place_filter_by_name(self):
        Place.objects.create(locality=self.locality, name="Other", place_type=PlaceType.REGION)
        response = self.client.get(reverse('place_list'), {'name': 'Region'})
        self.assertContains(response, "Region")
        self.assertNotContains(response, "Other")


class PlaceImportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="importer", password="pass")

        self.patcher = patch("cms.models.get_current_user", return_value=self.user)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")
        self.resource = PlaceResource()

    def test_invalid_relation_type(self):
        row = {
            'name': 'Test',
            'place_type': PlaceType.REGION,
            'locality': self.locality.abbreviation,
            'relation_type': 'invalid',
        }
        with self.assertRaises(ValueError) as cm:
            self.resource.before_import_row(row, row_number=1)
        self.assertIn('Invalid relation_type', str(cm.exception))

    def test_invalid_place_type(self):
        row = {
            'name': 'Test',
            'place_type': 'InvalidType',
            'locality': self.locality.abbreviation,
        }
        with self.assertRaises(ValueError) as cm:
            self.resource.before_import_row(row, row_number=1)
        self.assertIn('Invalid place_type', str(cm.exception))

    def test_related_place_must_share_locality(self):
        other_locality = Locality.objects.create(abbreviation="OT", name="Other")
        related = Place.objects.create(
            locality=other_locality,
            name="OtherRegion",
            place_type=PlaceType.REGION,
        )
        row = {
            'name': 'Test',
            'place_type': PlaceType.SITE,
            'locality': self.locality.abbreviation,
            'related_place': related.name,
            'relation_type': PlaceRelation.PART_OF,
        }
        with self.assertRaises(ValueError) as cm:
            self.resource.before_import_row(row, row_number=1)
        self.assertIn('must belong to locality', str(cm.exception))

    def test_prevent_circular_part_of(self):
        parent = Place.objects.create(
            locality=self.locality,
            name="Region",
            place_type=PlaceType.REGION,
        )
        child = Place.objects.create(
            locality=self.locality,
            name="Site",
            place_type=PlaceType.SITE,
            related_place=parent,
            relation_type=PlaceRelation.PART_OF,
        )
        row = {
            'name': parent.name,
            'place_type': parent.place_type,
            'locality': self.locality.abbreviation,
            'related_place': child.name,
            'relation_type': PlaceRelation.PART_OF,
        }
        with self.assertRaises(ValueError) as cm:
            self.resource.before_import_row(row, row_number=1)
        self.assertIn('higher-level place cannot be part of its descendant', str(cm.exception))


class UploadScanViewTests(TestCase):
    """Tests for the scan upload view and template link."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="cm", password="pass", is_staff=True)
        Group.objects.create(name="Collection Managers").user_set.add(self.user)
        self.url = reverse("admin-upload-scan")
        self.uploads_root = Path(settings.MEDIA_ROOT) / "uploads"
        self.addCleanup(self._cleanup_uploads)

    def _cleanup_uploads(self):
        if self.uploads_root.exists():
            shutil.rmtree(self.uploads_root)

    def test_login_required(self):
        response = self.client.get(self.url)
        # Anonymous users should be redirected to the login page
        self.assertEqual(response.status_code, 302)


    def test_admin_index_has_upload_link(self):
        self.client.login(username="cm", password="pass")
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, self.url)

    def test_form_has_multipart_enctype(self):
        self.client.login(username="cm", password="pass")
        response = self.client.get(self.url)
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_upload_saves_file(self):
        self.client.login(username="cm", password="pass")
        upload = SimpleUploadedFile("2025-01-01T010203.png", b"data", content_type="image/png")
        response = self.client.post(self.url, {"files": upload})
        self.assertEqual(response.status_code, 302)
        pending = Path(settings.MEDIA_ROOT) / "uploads" / "pending" / "2025-01-01T010203.png"
        self.assertTrue(pending.exists())
        self.assertTrue(Media.objects.filter(media_location=f"uploads/pending/2025-01-01T010203.png").exists())
        pending.unlink()
        import shutil
        shutil.rmtree(pending.parent.parent)

    def test_invalid_names_rejected(self):
        self.client.login(username="cm", password="pass")
        upload = SimpleUploadedFile("badname.png", b"data", content_type="image/png")
        response = self.client.post(self.url, {"files": upload})
        self.assertEqual(response.status_code, 302)
        rejected = Path(settings.MEDIA_ROOT) / "uploads" / "rejected" / "badname.png"
        self.assertTrue(rejected.exists())
        self.assertFalse(Media.objects.filter(media_location="uploads/rejected/badname.png").exists())
        rejected.unlink()
        shutil.rmtree(rejected.parent.parent)

    @override_settings(SCAN_UPLOAD_MAX_BYTES=10)
    def test_upload_rejects_oversized_file(self):
        self.client.login(username="cm", password="pass")
        upload = SimpleUploadedFile("2025-01-01T010203.png", b"x" * 11, content_type="image/png")
        response = self.client.post(self.url, {"files": upload})
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response,
            "form",
            "files",
            [
                "2025-01-01T010203.png is 11 bytes, which exceeds the 10 bytes limit per file.",
            ],
        )
        incoming = self.uploads_root / "incoming"
        if incoming.exists():
            self.assertFalse(any(incoming.iterdir()))

    @override_settings(SCAN_UPLOAD_MAX_BYTES=15)
    def test_upload_accepts_large_batch_when_each_file_is_valid(self):
        self.client.login(username="cm", password="pass")
        upload_one = SimpleUploadedFile("2025-01-01T010203.png", b"a" * 10, content_type="image/png")
        upload_two = SimpleUploadedFile("2025-01-01T010204.png", b"b" * 10, content_type="image/png")
        response = self.client.post(self.url, {"files": [upload_one, upload_two]}, follow=True)
        self.assertEqual(response.status_code, 200)
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertEqual(
            messages,
            [
                "Uploaded 2025-01-01T010203.png (1 of 2)",
                "Uploaded 2025-01-01T010204.png (2 of 2)",
            ],
        )
        pending = Path(settings.MEDIA_ROOT) / "uploads" / "pending"
        self.assertTrue(pending.exists())
        saved_files = {item.name for item in pending.iterdir()}
        self.assertSetEqual(saved_files, {"2025-01-01T010203.png", "2025-01-01T010204.png"})


class OcrViewTests(TestCase):
    """Tests for the OCR processing view and link."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="cm", password="pass", is_staff=True)
        Group.objects.create(name="Collection Managers").user_set.add(self.user)
        self.url = reverse("admin-do-ocr")
        self.loop_url = f"{self.url}?loop=1"
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_login_required(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_admin_index_has_ocr_link(self):
        self.client.login(username="cm", password="pass")
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, self.loop_url)

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch(
        "cms.ocr_processing.chatgpt_ocr",
        return_value=with_usage({"foo": "bar"}, usage_overrides={"remaining_quota_usd": 11.0}),
    )
    def test_ocr_moves_file_and_saves_json(self, mock_ocr, mock_detect):
        self.client.login(username="cm", password="pass")
        pending = Path(settings.MEDIA_ROOT) / "uploads" / "pending"
        pending.mkdir(parents=True, exist_ok=True)
        filename = "2025-01-01T010203.png"
        file_path = pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        ocr_file = Path(settings.MEDIA_ROOT) / "uploads" / "ocr" / filename
        self.assertTrue(ocr_file.exists())
        media = Media.objects.get()
        self.assertEqual(media.ocr_status, Media.OCRStatus.COMPLETED)
        self.assertEqual(media.media_location.name, f"uploads/ocr/{filename}")
        self.assertEqual(media.ocr_data["foo"], "bar")
        usage_data = media.ocr_data["usage"]
        for key, value in DEFAULT_USAGE_PAYLOAD.items():
            self.assertEqual(usage_data[key], value)
        self.assertIn("processing_seconds", usage_data)
        self.assertGreaterEqual(usage_data["processing_seconds"], 0)
        usage_record = media.llm_usage_record
        self.assertEqual(usage_record.model_name, DEFAULT_USAGE_PAYLOAD["model"])
        self.assertEqual(usage_record.prompt_tokens, DEFAULT_USAGE_PAYLOAD["prompt_tokens"])
        self.assertEqual(usage_record.completion_tokens, DEFAULT_USAGE_PAYLOAD["completion_tokens"])
        self.assertEqual(usage_record.total_tokens, DEFAULT_USAGE_PAYLOAD["total_tokens"])
        self.assertEqual(
            usage_record.cost_usd,
            Decimal(str(DEFAULT_USAGE_PAYLOAD["total_cost_usd"])),
        )
        self.assertEqual(usage_record.response_id, DEFAULT_USAGE_PAYLOAD["request_id"])
        self.assertEqual(usage_record.remaining_quota_usd, Decimal("11.0"))
        self.assertIsNotNone(usage_record.processing_seconds)
        self.assertGreaterEqual(float(usage_record.processing_seconds), 0.0)
        import shutil
        shutil.rmtree(pending.parent)

    @patch(
        "cms.views.process_pending_scans",
        return_value=(0, 1, 1, ["test.png: boom"], None, ["test.png"]),
    )
    def test_do_ocr_shows_error_details(self, mock_process):
        self.client.login(username="cm", password="pass")
        response = self.client.get(self.url, follow=True)
        self.assertContains(response, "Processed 0 of 1 scans this run. Latest scan: test.png.")
        self.assertContains(response, "OCR failed for 1 scans: test.png")

    @patch(
        "cms.views.process_pending_scans",
        return_value=(3, 0, 5, [], None, ["scan-5.png"]),
    )
    def test_do_ocr_reports_progress(self, mock_process):
        self.client.login(username="cm", password="pass")
        response = self.client.get(self.url, follow=True)
        self.assertContains(response, "Processed 3 of 5 scans this run. Latest scan: scan-5.png.")

    @patch("cms.views._count_pending_scans", return_value=4)
    @patch("cms.views.process_pending_scans", return_value=(1, 0, 1, [], None, ["scan-1.png"]))
    def test_loop_mode_auto_refreshes(self, mock_process, mock_count):
        self.client.login(username="cm", password="pass")
        response = self.client.get(self.loop_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Refresh"], f"0;url={self.loop_url}")
        body = response.content.decode()
        self.assertIn("Continuing OCR… scan 1 of 5 (Latest: scan-1.png).", body)
        session = self.client.session
        self.assertEqual(session["ocr_loop_stats"]["successes"], 1)
        self.assertEqual(session["ocr_loop_stats"]["attempted"], 1)
        self.assertEqual(session["ocr_loop_stats"]["latest_filename"], "scan-1.png")

    @patch("cms.views._count_pending_scans", return_value=99)
    @patch("cms.views.process_pending_scans", return_value=(1, 0, 1, [], None, ["scan-1.png"]))
    def test_loop_mode_uses_limit_for_expected_total(self, mock_process, mock_count):
        self.client.login(username="cm", password="pass")
        url = f"{self.loop_url}&limit=100"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Continuing OCR… scan 1 of 100 (Latest: scan-1.png).", response.content.decode())
        self.assertEqual(response["Refresh"], f"0;url={url}")

    @patch("cms.views._count_pending_scans")
    @patch("cms.views.process_pending_scans")
    def test_loop_mode_finalizes_and_reports(self, mock_process, mock_count):
        self.client.login(username="cm", password="pass")
        mock_process.side_effect = [
            (1, 0, 1, [], None, ["scan-1.png"]),
            (1, 0, 1, [], None, ["scan-2.png"]),
        ]
        mock_count.side_effect = [2, 0]

        first = self.client.get(self.loop_url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first["Refresh"], f"0;url={self.loop_url}")

        final = self.client.get(self.loop_url, follow=True)
        self.assertContains(final, "Processed 2 of 2 scans this run. Latest scan: scan-2.png.")
        self.assertIsNone(self.client.session.get("ocr_loop_stats"))

    @patch("cms.views._count_pending_scans", return_value=5)
    @patch(
        "cms.views.process_pending_scans",
        return_value=(0, 1, 1, ["jam.png: timeout"], "jam.png", ["jam.png"]),
    )
    def test_loop_mode_stops_on_jam(self, mock_process, mock_count):
        self.client.login(username="cm", password="pass")
        response = self.client.get(self.loop_url, follow=True)
        self.assertContains(response, "OCR failed for 1 scans: jam.png")
        self.assertContains(
            response,
            "OCR halted because scan jam.png timed out after three attempts. Please investigate before retrying.",
        )


class ProcessPendingScansTests(TestCase):
    def setUp(self):
        import shutil

        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="pass")
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.pending = Path(settings.MEDIA_ROOT) / "uploads" / "pending"
        self.pending.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.pending.parent, ignore_errors=True))

    @patch("cms.ocr_processing.detect_card_type", side_effect=Exception("boom"))
    def test_failure_logs_and_records_error(self, mock_detect):
        filename = "error.png"
        file_path = self.pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")
        with self.assertLogs("cms.ocr_processing", level="ERROR") as cm:
            successes, failures, total, errors, jammed, processed = process_pending_scans()
        self.assertEqual(successes, 0)
        self.assertEqual(failures, 1)
        self.assertEqual(total, 1)
        self.assertTrue(any("boom" in e for e in errors))
        self.assertTrue(any("boom" in m for m in cm.output))
        self.assertIsNone(jammed)
        self.assertEqual(processed, [filename])
        media = Media.objects.get()
        self.assertEqual(media.ocr_status, Media.OCRStatus.FAILED)
        self.assertEqual(media.ocr_data["error"], "boom")
        self.assertEqual(media.media_location.name, f"uploads/failed/{filename}")
        failed_file = Path(settings.MEDIA_ROOT) / "uploads" / "failed" / filename
        self.assertTrue(failed_file.exists())

    @patch("cms.ocr_processing.time.sleep")
    @patch("cms.ocr_processing.detect_card_type", side_effect=TimeoutError("timeout"))
    def test_timeout_retries_and_stops_queue(self, mock_sleep, mock_detect):
        filename1 = "jam.png"
        filename2 = "next.png"
        (self.pending / filename1).write_bytes(b"data")
        (self.pending / filename2).write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename1}")
        Media.objects.create(media_location=f"uploads/pending/{filename2}")

        successes, failures, total, errors, jammed, processed = process_pending_scans(limit=5)

        self.assertEqual(successes, 0)
        self.assertEqual(failures, 1)
        self.assertEqual(total, 1)
        self.assertEqual(jammed, filename1)
        self.assertTrue(any("timeout" in e for e in errors))
        self.assertEqual(mock_detect.call_count, 3)
        self.assertGreaterEqual(mock_sleep.call_count, 2)
        self.assertTrue((self.pending / filename2).exists())
        failed_file = Path(settings.MEDIA_ROOT) / "uploads" / "failed" / filename1
        self.assertTrue(failed_file.exists())
        self.assertEqual(processed, [filename1])

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch(
        "cms.ocr_processing.chatgpt_ocr",
        return_value=with_usage({
            "accessions": [
                {
                    "collection_abbreviation": {"interpreted": "KNM"},
                    "specimen_prefix_abbreviation": {"interpreted": "AB"},
                    "specimen_no": {"interpreted": 123},
                    "type_status": {"interpreted": "Holotype"},
                    "published": {"interpreted": "Yes"},
                    "additional_notes": [
                        {
                            "heading": {"interpreted": "Note"},
                            "value": {"interpreted": "something"},
                        }
                    ],
                    "references": [
                        {
                            "reference_first_author": {"interpreted": "Harris"},
                            "reference_title": {"interpreted": "Lothagam"},
                            "reference_year": {"interpreted": "2003"},
                            "page": {"interpreted": "485-519"},
                        }
                    ],
                }
            ]
        }),
    )
    def test_creates_accession_and_links_media(self, mock_ocr, mock_detect):
        Collection.objects.create(abbreviation="KNM", description="Kenya")
        filename = "acc.png"
        file_path = self.pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")
        successes, failures, total, errors, jammed, processed = process_pending_scans()
        self.assertEqual((successes, failures, total), (1, 0, 1))
        self.assertIsNone(jammed)
        self.assertEqual(processed, [filename])
        self.assertEqual(Accession.objects.count(), 0)
        media = Media.objects.get()
        self.assertEqual(media.ocr_status, Media.OCRStatus.COMPLETED)
        self.assertEqual(media.qc_status, Media.QCStatus.PENDING_INTERN)
        result = media.transition_qc(Media.QCStatus.APPROVED, user=self.user)
        self.assertEqual(result["conflicts"], [])
        self.assertEqual(len(result["created"]), 1)
        accession = Accession.objects.get()
        self.assertEqual(accession.collection.abbreviation, "KNM")
        self.assertEqual(accession.specimen_prefix.abbreviation, "AB")
        self.assertEqual(accession.specimen_no, 123)
        self.assertEqual(accession.instance_number, 1)
        self.assertEqual(accession.type_status, "Holotype")
        self.assertTrue(accession.is_published)
        self.assertIn("Note: something", accession.comment)
        reference = Reference.objects.get()
        self.assertEqual(reference.first_author, "Harris")
        self.assertEqual(reference.title, "Lothagam")
        self.assertEqual(reference.year, "2003")
        self.assertEqual(reference.citation, "Harris (2003) Lothagam")
        link = AccessionReference.objects.get()
        self.assertEqual(link.accession, accession)
        self.assertEqual(link.reference, reference)
        self.assertEqual(link.page, "485-519")
        media.refresh_from_db()
        self.assertEqual(media.accession, accession)
        self.assertEqual(media.qc_status, Media.QCStatus.APPROVED)
        usage_data = media.ocr_data["usage"]
        for key, value in DEFAULT_USAGE_PAYLOAD.items():
            self.assertEqual(usage_data[key], value)
        self.assertIn("processing_seconds", usage_data)
        self.assertGreaterEqual(usage_data["processing_seconds"], 0)
        usage_record = media.llm_usage_record
        self.assertEqual(usage_record.total_tokens, DEFAULT_USAGE_PAYLOAD["total_tokens"])
        self.assertIsNotNone(usage_record.processing_seconds)
        self.assertIn("_processed_accessions", media.ocr_data)
        repeat = media.transition_qc(Media.QCStatus.APPROVED, user=self.user)
        self.assertEqual(repeat["created"], [])
        self.assertEqual(Accession.objects.count(), 1)

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch(
        "cms.ocr_processing.chatgpt_ocr",
        return_value=with_usage({
            "accessions": [
                {
                    "collection_abbreviation": {"interpreted": "KNM"},
                    "specimen_prefix_abbreviation": {"interpreted": "AB"},
                    "specimen_no": {"interpreted": 123},
                    "type_status": {"interpreted": "Holotype"},
                    "published": {"interpreted": "Yes"},
                    "references": [
                        {
                            "reference_first_author": {"interpreted": "Harris"},
                            "reference_title": {"interpreted": "Lothagam"},
                            "reference_year": {"interpreted": "2003"},
                            "page": {"interpreted": "500"},
                        }
                    ],
                }
            ]
        }),
    )
    def test_reuses_existing_reference(self, mock_ocr, mock_detect):
        Collection.objects.create(abbreviation="KNM", description="Kenya")
        reference = Reference.objects.create(
            first_author="Harris",
            title="Lothagam",
            year="2003",
            citation="Harris (2003) Lothagam",
        )
        filename = "acc_ref.png"
        file_path = self.pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")
        process_pending_scans()
        self.assertEqual(Reference.objects.count(), 1)
        media = Media.objects.get()
        media.transition_qc(Media.QCStatus.APPROVED, user=self.user)
        accession = Accession.objects.get()
        link = AccessionReference.objects.get()
        self.assertEqual(link.accession, accession)
        self.assertEqual(link.reference, reference)
        self.assertEqual(link.page, "500")

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch("cms.ocr_processing.chatgpt_ocr")
    def test_reference_reused_across_scans_with_variants(self, mock_ocr, mock_detect):
        Collection.objects.create(abbreviation="KNM", description="Kenya")
        mock_ocr.side_effect = [
            with_usage({
                "accessions": [
                    {
                        "collection_abbreviation": {"interpreted": "KNM"},
                        "specimen_prefix_abbreviation": {"interpreted": "AB"},
                        "specimen_no": {"interpreted": 123},
                        "type_status": {"interpreted": "Holotype"},
                        "published": {"interpreted": "Yes"},
                        "references": [
                            {
                                "reference_first_author": {"interpreted": "Harris"},
                                "reference_title": {"interpreted": "Lothagam"},
                                "reference_year": {"interpreted": "2003"},
                            }
                        ],
                    }
                ]
            }),
            with_usage({
                "accessions": [
                    {
                        "collection_abbreviation": {"interpreted": "KNM"},
                        "specimen_prefix_abbreviation": {"interpreted": "AB"},
                        "specimen_no": {"interpreted": 124},
                        "type_status": {"interpreted": "Holotype"},
                        "published": {"interpreted": "Yes"},
                        "references": [
                            {
                                "reference_first_author": {"interpreted": "harris "},
                                "reference_title": {"interpreted": "lothagam "},
                                "reference_year": {"interpreted": "2003 "},
                            }
                        ],
                    }
                ]
            }),
        ]

        filename1 = "acc_ref1.png"
        file_path1 = self.pending / filename1
        file_path1.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename1}")
        process_pending_scans()
        media1 = Media.objects.get(media_location=f"uploads/ocr/{filename1}")
        media1.transition_qc(Media.QCStatus.APPROVED, user=self.user)

        self.assertEqual(Reference.objects.count(), 1)
        reference = Reference.objects.get()

        filename2 = "acc_ref2.png"
        file_path2 = self.pending / filename2
        file_path2.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename2}")
        process_pending_scans()
        media2 = Media.objects.get(media_location=f"uploads/ocr/{filename2}")
        media2.transition_qc(Media.QCStatus.APPROVED, user=self.user)

        self.assertEqual(Reference.objects.count(), 1)
        links = AccessionReference.objects.all()
        self.assertEqual(links.count(), 2)
        for link in links:
            self.assertEqual(link.reference, reference)

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch(
        "cms.ocr_processing.chatgpt_ocr",
        return_value=with_usage({
            "accessions": [
                {
                    "collection_abbreviation": {"interpreted": "KNM"},
                    "specimen_prefix_abbreviation": {"interpreted": "AB"},
                    "specimen_no": {"interpreted": 123},
                    "type_status": {"interpreted": "Type"},
                    "published": {"interpreted": "No"},
                    "additional_notes": [],
                }
            ]
        }),
    )
    def test_existing_accession_reports_conflict(self, mock_ocr, mock_detect):
        collection = Collection.objects.create(abbreviation="KNM", description="Kenya")
        locality = Locality.objects.create(abbreviation="AB", name="Existing")
        Accession.objects.create(collection=collection, specimen_prefix=locality, specimen_no=123)
        filename = "acc2.png"
        file_path = self.pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")
        successes, failures, total, errors, jammed, processed = process_pending_scans()
        self.assertEqual((successes, failures, total), (1, 0, 1))
        self.assertIsNone(jammed)
        self.assertEqual(processed, [filename])
        media = Media.objects.get()
        with self.assertRaises(ValidationError) as exc:
            media.transition_qc(Media.QCStatus.APPROVED, user=self.user)
        self.assertIn("Existing accession detected", str(exc.exception))
        self.assertEqual(Accession.objects.count(), 1)
        media.refresh_from_db()
        self.assertEqual(media.qc_status, Media.QCStatus.PENDING_INTERN)
        self.assertEqual(media.qc_logs.filter(description__contains="Approval blocked").count(), 1)

    def test_transition_with_resolution_creates_new_instance(self):
        collection = Collection.objects.create(abbreviation="KNM", description="Kenya")
        locality = Locality.objects.create(abbreviation="AB", name="Area 1")
        Accession.objects.create(collection=collection, specimen_prefix=locality, specimen_no=123)
        media = self.create_media(
            qc_status=Media.QCStatus.PENDING_EXPERT,
            ocr_data={
                "card_type": "accession_card",
                "accessions": [
                    {
                        "collection_abbreviation": {"interpreted": "KNM"},
                        "specimen_prefix_abbreviation": {"interpreted": "AB"},
                        "specimen_no": {"interpreted": 123},
                    }
                ],
            },
        )
        key = f"{collection.abbreviation}:{locality.abbreviation}:123"
        result = media.transition_qc(
            Media.QCStatus.APPROVED,
            user=self.user,
            resolution={key: {"action": "new_instance"}},
        )

        accessions = Accession.objects.filter(
            collection=collection,
            specimen_prefix=locality,
            specimen_no=123,
        ).order_by("instance_number")
        self.assertEqual(accessions.count(), 2)
        self.assertEqual(accessions.last().instance_number, accessions.first().instance_number + 1)
        media.refresh_from_db()
        self.assertEqual(media.accession, accessions.last())
        self.assertEqual(len(result["created"]), 1)

    def test_transition_with_resolution_updates_existing(self):
        collection = Collection.objects.create(abbreviation="KNM", description="Kenya")
        locality = Locality.objects.create(abbreviation="AB", name="Area 1")
        accession = Accession.objects.create(
            collection=collection,
            specimen_prefix=locality,
            specimen_no=123,
            comment="Original",
        )
        AccessionRow.objects.create(accession=accession, specimen_suffix="-")
        media = self.create_media(
            qc_status=Media.QCStatus.PENDING_EXPERT,
            ocr_data={
                "card_type": "accession_card",
                "accessions": [
                    {
                        "collection_abbreviation": {"interpreted": "KNM"},
                        "specimen_prefix_abbreviation": {"interpreted": "AB"},
                        "specimen_no": {"interpreted": 123},
                        "additional_notes": [
                            {
                                "heading": {"interpreted": "Note"},
                                "value": {"interpreted": "Updated guidance"},
                            }
                        ],
                        "rows": [
                            {
                                "specimen_suffix": {"interpreted": "-"},
                                "storage_area": {"interpreted": "Shelf 42"},
                            }
                        ],
                    }
                ],
            },
        )

        key = f"{collection.abbreviation}:{locality.abbreviation}:123"
        resolution = {
            key: {
                "action": "update_existing",
                "accession_id": accession.pk,
                "fields": {"comment": "Note: Updated guidance"},
                "rows": ["-"],
                "references": [],
                "field_slips": [],
            }
        }

        result = media.transition_qc(
            Media.QCStatus.APPROVED,
            user=self.user,
            resolution=resolution,
        )

        media.refresh_from_db()
        accession.refresh_from_db()
        self.assertEqual(media.accession, accession)
        self.assertEqual(accession.comment, "Note: Updated guidance")
        row = accession.accessionrow_set.get(specimen_suffix="-")
        self.assertEqual(row.storage.area, "Shelf 42")
        self.assertEqual(result["created"], [])
        processed = media.ocr_data.get("_processed_accessions") or []
        self.assertTrue(any(entry.get("accession_id") == accession.pk for entry in processed))

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch(
        "cms.ocr_processing.chatgpt_ocr",
        return_value=with_usage({
            "accessions": [
                {
                    "collection_abbreviation": {"interpreted": "KNM"},
                    "specimen_prefix_abbreviation": {"interpreted": "AB"},
                    "specimen_no": {"interpreted": 123},
                    "type_status": {"interpreted": "Holotype"},
                    "published": {"interpreted": "Yes"},
                    "field_slips": [
                        {
                            "field_number": {"interpreted": "FS-1"},
                            "verbatim_locality": {"interpreted": "Loc1"},
                            "verbatim_taxon": {"interpreted": "Homo"},
                            "verbatim_element": {"interpreted": "Femur"},
                            "verbatim_horizon": {
                                "formation": {"interpreted": "Form"},
                                "member": {"interpreted": "Member"},
                                "bed_or_horizon": {"interpreted": "Bed"},
                                "chronostratigraphy": {"interpreted": None},
                            },
                            "aerial_photo": {"interpreted": "P1"},
                            "verbatim_latitude": {"interpreted": "Lat"},
                            "verbatim_longitude": {"interpreted": "Lon"},
                            "verbatim_elevation": {"interpreted": "100"},
                        }
                    ],
                }
            ]
        }),
    )
    def test_creates_field_slip_and_links(self, mock_ocr, mock_detect):
        Collection.objects.create(abbreviation="KNM", description="Kenya")
        filename = "acc_fs.png"
        file_path = self.pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")
        process_pending_scans()
        media = Media.objects.get()
        media.transition_qc(Media.QCStatus.APPROVED, user=self.user)
        accession = Accession.objects.get()
        field_slip = FieldSlip.objects.get()
        link = AccessionFieldSlip.objects.get()
        self.assertEqual(link.accession, accession)
        self.assertEqual(link.fieldslip, field_slip)
        self.assertEqual(field_slip.field_number, "FS-1")
        self.assertEqual(field_slip.verbatim_locality, "Loc1")
        self.assertEqual(field_slip.verbatim_taxon, "Homo")
        self.assertEqual(field_slip.verbatim_element, "Femur")
        self.assertEqual(field_slip.verbatim_horizon, "Form | Member | Bed")
        self.assertEqual(field_slip.aerial_photo, "P1")
        self.assertEqual(field_slip.verbatim_latitude, "Lat")
        self.assertEqual(field_slip.verbatim_longitude, "Lon")
        self.assertEqual(field_slip.verbatim_elevation, "100")

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch(
        "cms.ocr_processing.chatgpt_ocr",
        return_value=with_usage({
            "accessions": [
                {
                    "collection_abbreviation": {"interpreted": "KNM"},
                    "specimen_prefix_abbreviation": {"interpreted": "AB"},
                    "specimen_no": {"interpreted": 123},
                    "type_status": {"interpreted": "Holotype"},
                    "published": {"interpreted": "Yes"},
                    "field_slips": [
                        {
                            "field_number": {"interpreted": "FS-1"},
                            "verbatim_locality": {"interpreted": "Loc1"},
                            "verbatim_taxon": {"interpreted": "Homo"},
                            "verbatim_element": {"interpreted": "Femur"},
                        }
                    ],
                }
            ]
        }),
    )
    def test_reuses_existing_field_slip(self, mock_ocr, mock_detect):
        Collection.objects.create(abbreviation="KNM", description="Kenya")
        existing = FieldSlip.objects.create(
            field_number="FS-1",
            verbatim_locality="Loc1",
            verbatim_taxon="Homo",
            verbatim_element="Femur",
        )
        filename = "acc_fs2.png"
        file_path = self.pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")
        process_pending_scans()
        media = Media.objects.get()
        media.transition_qc(Media.QCStatus.APPROVED, user=self.user)
        self.assertEqual(FieldSlip.objects.count(), 1)
        link = AccessionFieldSlip.objects.get()
        self.assertEqual(link.fieldslip, existing)

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch(
        "cms.ocr_processing.chatgpt_ocr",
        return_value=with_usage({
            "accessions": [
                {
                    "collection_abbreviation": {"interpreted": "KNM"},
                    "specimen_prefix_abbreviation": {"interpreted": "AB"},
                    "specimen_no": {"interpreted": 123},
                    "type_status": {"interpreted": "Holotype"},
                    "published": {"interpreted": "Yes"},
                    "field_slips": [
                        {
                            "field_number": {"interpreted": None},
                            "verbatim_locality": {"interpreted": "Loc1"},
                            "verbatim_taxon": {"interpreted": "Homo"},
                            "verbatim_element": {"interpreted": "Femur"},
                        }
                    ],
                }
            ]
        }),
    )
    def test_creates_field_slip_when_field_number_missing(
        self, mock_ocr, mock_detect
    ):
        Collection.objects.create(abbreviation="KNM", description="Kenya")
        filename = "acc_fs_unknown.png"
        file_path = self.pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")
        process_pending_scans()
        media = Media.objects.get()
        media.transition_qc(Media.QCStatus.APPROVED, user=self.user)

        self.assertEqual(FieldSlip.objects.count(), 1)
        field_slip = FieldSlip.objects.get()
        self.assertTrue(
            field_slip.field_number.startswith(UNKNOWN_FIELD_NUMBER_PREFIX)
        )
        self.assertEqual(field_slip.verbatim_locality, "Loc1")
        self.assertEqual(field_slip.verbatim_taxon, "Homo")
        self.assertEqual(field_slip.verbatim_element, "Femur")

        self.assertEqual(AccessionFieldSlip.objects.count(), 1)
        link = AccessionFieldSlip.objects.get()
        accession = Accession.objects.get()
        self.assertEqual(link.accession, accession)
        self.assertEqual(link.fieldslip, field_slip)


    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch(
        "cms.ocr_processing.chatgpt_ocr",
        return_value=with_usage({
            "accessions": [
                {
                    "collection_abbreviation": {"interpreted": "KNM"},
                    "specimen_prefix_abbreviation": {"interpreted": "AB"},
                    "specimen_no": {"interpreted": 123},
                    "rows": [
                        {
                            "specimen_suffix": {"interpreted": "A"},
                            "storage_area": {"interpreted": "99AA"},
                        }
                    ],
                }
            ]
        }),
    )
    def test_creates_rows_and_storage(self, mock_ocr, mock_detect):
        Collection.objects.create(abbreviation="KNM", description="Kenya")
        filename = "acc_row.png"
        file_path = self.pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")
        process_pending_scans()
        media = Media.objects.get()
        media.transition_qc(Media.QCStatus.APPROVED, user=self.user)
        accession = Accession.objects.get()
        row = AccessionRow.objects.get()
        self.assertEqual(row.accession, accession)
        self.assertEqual(row.specimen_suffix, "A")
        self.assertEqual(row.status, InventoryStatus.UNKNOWN)
        self.assertIsNotNone(row.storage)
        self.assertEqual(row.storage.area, "99AA")
        self.assertEqual(row.storage.parent_area.area, "-Undefined")

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch(
        "cms.ocr_processing.chatgpt_ocr",
        return_value=with_usage({
            "accessions": [
                {
                    "collection_abbreviation": {"interpreted": "KNM"},
                    "specimen_prefix_abbreviation": {"interpreted": "AB"},
                    "specimen_no": {"interpreted": 123},
                    "rows": [
                        {
                            "specimen_suffix": {"interpreted": "A"},
                            "storage_area": {"interpreted": "99AA"},
                        },
                        {
                            "specimen_suffix": {"interpreted": "A"},
                            "storage_area": {"interpreted": "99AA"},
                        },
                    ],
                }
            ]
        }),
    )
    def test_reuses_existing_row(self, mock_ocr, mock_detect):
        Collection.objects.create(abbreviation="KNM", description="Kenya")
        filename = "acc_row_dup.png"
        file_path = self.pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")
        process_pending_scans()
        media = Media.objects.get()
        media.transition_qc(Media.QCStatus.APPROVED, user=self.user)
        self.assertEqual(AccessionRow.objects.count(), 1)

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch(
        "cms.ocr_processing.chatgpt_ocr",
        return_value=with_usage({
            "accessions": [
                {
                    "collection_abbreviation": {"interpreted": "KNM"},
                    "specimen_prefix_abbreviation": {"interpreted": "AB"},
                    "specimen_no": {"interpreted": 124},
                    "rows": [
                        {"specimen_suffix": {"interpreted": "-"}}
                    ],
                }
            ]
        }),
    )
    def test_preserves_dash_suffix(self, mock_ocr, mock_detect):
        Collection.objects.create(abbreviation="KNM", description="Kenya")
        filename = "acc_row_dash.png"
        file_path = self.pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")
        process_pending_scans()
        media = Media.objects.get()
        media.transition_qc(Media.QCStatus.APPROVED, user=self.user)
        row = AccessionRow.objects.get()
        self.assertEqual(row.specimen_suffix, "-")

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch(
        "cms.ocr_processing.chatgpt_ocr",
        return_value=with_usage({
            "accessions": [
                {
                    "collection_abbreviation": {"interpreted": "KNM"},
                    "specimen_prefix_abbreviation": {"interpreted": "AB"},
                    "specimen_no": {"interpreted": 123},
                    "rows": [
                        {"specimen_suffix": {"interpreted": "A"}}
                    ],
                    "identifications": [
                        {
                            "taxon": {"interpreted": "Homo habilis"},
                            "identification_qualifier": {"interpreted": "cf."},
                            "verbatim_identification": {"interpreted": "cf. Homo habilis"},
                            "identification_remarks": {"interpreted": "Primates|Hominidae|Homo|habilis"},
                        }
                    ],
                }
            ]
        }),
    )
    def test_creates_identifications_for_rows(self, mock_ocr, mock_detect):
        Collection.objects.create(abbreviation="KNM", description="Kenya")
        filename = "acc_ident.png"
        file_path = self.pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")
        process_pending_scans()
        media = Media.objects.get()
        media.transition_qc(Media.QCStatus.APPROVED, user=self.user)
        row = AccessionRow.objects.get()
        ident = Identification.objects.get()
        self.assertEqual(ident.accession_row, row)
        self.assertEqual(ident.taxon, "Homo habilis")
        self.assertEqual(ident.identification_qualifier, "cf.")
        self.assertEqual(ident.verbatim_identification, "cf. Homo habilis")
        self.assertEqual(ident.identification_remarks, "Primates|Hominidae|Homo|habilis")

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch(
        "cms.ocr_processing.chatgpt_ocr",
        return_value=with_usage({
            "accessions": [
                {
                    "collection_abbreviation": {"interpreted": "KNM"},
                    "specimen_prefix_abbreviation": {"interpreted": "AB"},
                    "specimen_no": {"interpreted": 123},
                    "rows": [
                        {
                            "specimen_suffix": {"interpreted": "A"},
                            "natures": [
                                {
                                    "element_name": {"interpreted": "Femur"},
                                    "side": {"interpreted": "Left"},
                                    "condition": {"interpreted": "Intact"},
                                    "verbatim_element": {"interpreted": "Left Femur"},
                                    "portion": {"interpreted": "proximal"},
                                    "fragments": {"interpreted": 1},
                                }
                            ],
                        }
                    ],
                }
            ]
        }),
    )
    def test_creates_natures_for_rows(self, mock_ocr, mock_detect):
        Collection.objects.create(abbreviation="KNM", description="Kenya")
        filename = "acc_nature.png"
        file_path = self.pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")
        process_pending_scans()
        media = Media.objects.get()
        media.transition_qc(Media.QCStatus.APPROVED, user=self.user)
        row = AccessionRow.objects.get()
        nature = NatureOfSpecimen.objects.get()
        self.assertEqual(nature.accession_row, row)
        self.assertEqual(nature.element.name, "Femur")
        self.assertEqual(nature.element.parent_element.name, "-Undefined")
        self.assertEqual(nature.side, "Left")
        self.assertEqual(nature.condition, "Intact")
        self.assertEqual(nature.verbatim_element, "Left Femur")
        self.assertEqual(nature.portion, "proximal")
        self.assertEqual(nature.fragments, 1)

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch(
        "cms.ocr_processing.chatgpt_ocr",
        return_value=with_usage({
            "accessions": [
                {
                    "collection_abbreviation": {"interpreted": "KNM"},
                    "specimen_prefix_abbreviation": {"interpreted": "AB"},
                    "specimen_no": {"interpreted": 123},
                    "rows": [
                        {
                            "specimen_suffix": {"interpreted": f"S{i:03d}"},
                        }
                        for i in range(MAX_OCR_ROWS_PER_ACCESSION + 5)
                    ],
                }
            ]
        }),
    )
    def test_limits_rows_to_maximum(self, mock_ocr, mock_detect):
        Collection.objects.create(abbreviation="KNM", description="Kenya")
        Locality.objects.create(abbreviation="AB", name="Area 1")
        filename = "acc_row_limit.png"
        file_path = self.pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")

        with self.assertLogs("cms.ocr_processing", level="WARNING") as cm:
            process_pending_scans()

        self.assertTrue(
            any("Truncated OCR rows" in message for message in cm.output),
            cm.output,
        )

        media = Media.objects.get()
        result = media.transition_qc(Media.QCStatus.APPROVED, user=self.user)
        self.assertEqual(len(result["created"]), 1)
        accession = Accession.objects.get()
        rows = accession.accessionrow_set.order_by("specimen_suffix")
        self.assertEqual(rows.count(), MAX_OCR_ROWS_PER_ACCESSION)
        suffixes = list(rows.values_list("specimen_suffix", flat=True))
        self.assertIn("S000", suffixes)
        self.assertNotIn(f"S{MAX_OCR_ROWS_PER_ACCESSION:03d}", suffixes)

class MediaTransitionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="reviewer", password="pass")
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)

    def create_media(self, **overrides):
        data = {
            "media_location": "uploads/pending/test.png",
        }
        data.update(overrides)
        return Media.objects.create(**data)

    def test_transition_updates_metadata_and_logs(self):
        media = self.create_media()
        media.transition_qc(Media.QCStatus.PENDING_EXPERT, user=self.user, note="Ready for expert")
        media.refresh_from_db()
        self.assertEqual(media.qc_status, Media.QCStatus.PENDING_EXPERT)
        self.assertEqual(media.intern_checked_by, self.user)
        self.assertIsNotNone(media.intern_checked_on)
        log = media.qc_logs.first()
        self.assertIn("Ready for expert", log.description)
        self.assertEqual(log.changed_by, self.user)

    def test_transition_to_approved_creates_accession_and_stamps_expert(self):
        Collection.objects.create(abbreviation="KNM", description="Kenya")
        Locality.objects.create(abbreviation="AB", name="Area 1")
        media = self.create_media(
            ocr_data={
                "card_type": "accession_card",
                "accessions": [
                    {
                        "collection_abbreviation": {"interpreted": "KNM"},
                        "specimen_prefix_abbreviation": {"interpreted": "AB"},
                        "specimen_no": {"interpreted": 321},
                    }
                ],
            }
        )
        result = media.transition_qc(Media.QCStatus.APPROVED, user=self.user, note="Looks good")
        self.assertEqual(result["conflicts"], [])
        media.refresh_from_db()
        self.assertEqual(media.qc_status, Media.QCStatus.APPROVED)
        self.assertEqual(media.expert_checked_by, self.user)
        self.assertIsNotNone(media.expert_checked_on)
        self.assertEqual(Accession.objects.count(), 1)
        log = media.qc_logs.filter(change_type=MediaQCLog.ChangeType.STATUS).first()
        self.assertIn("Looks good", log.description)

    def test_invalid_transition_raises_validation_error(self):
        media = self.create_media(qc_status=Media.QCStatus.APPROVED, ocr_data={"card_type": "other"})
        with self.assertRaises(ValidationError):
            media.transition_qc(Media.QCStatus.REJECTED, user=self.user)


class MediaExpertQCWizardTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.expert = User.objects.create_user(username="expert", password="pass")

        patcher = patch("cms.models.get_current_user", return_value=self.expert)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.curators_group = Group.objects.create(name="Curators")
        self.curators_group.user_set.add(self.expert)

        self.collection = Collection.objects.create(abbreviation="KNM", description="Kenya")
        self.locality = Locality.objects.create(abbreviation="AB", name="Area 1")

        self.media = Media.objects.create(
            media_location="uploads/ocr/expert.png",
            qc_status=Media.QCStatus.PENDING_EXPERT,
            ocr_status=Media.OCRStatus.COMPLETED,
            ocr_data={
                "card_type": "accession_card",
                "accessions": [
                    {
                        "collection_abbreviation": {"interpreted": "KNM"},
                        "specimen_prefix_abbreviation": {"interpreted": "AB"},
                        "specimen_no": {"interpreted": 123},
                        "rows": [
                            {
                                "_row_id": "row-0",
                                "specimen_suffix": {"interpreted": "-"},
                            }
                        ],
                    }
                ],
            },
        )

        self.client.force_login(self.expert)

    def test_context_includes_recent_history(self):
        log = MediaQCLog.objects.create(
            media=self.media,
            change_type=MediaQCLog.ChangeType.STATUS,
            field_name="qc_status",
            old_value={"qc_status": Media.QCStatus.PENDING_EXPERT},
            new_value={"qc_status": Media.QCStatus.APPROVED},
            description="Approved after review.",
            changed_by=self.expert,
        )
        MediaQCComment.objects.create(
            log=log,
            comment="Resolved outstanding warnings.",
            created_by=self.expert,
        )

        response = self.client.get(reverse("media_expert_qc", args=[self.media.uuid]))
        self.assertEqual(response.status_code, 200)
        history = response.context["qc_history_logs"]
        self.assertTrue(history)
        self.assertEqual(history[0], log)
        comments = list(history[0].comments.all())
        self.assertEqual(comments[0].comment, "Resolved outstanding warnings.")

    def add_unlinked_identification_warning(self):
        data = copy.deepcopy(self.media.ocr_data)
        accessions = data.setdefault("accessions", [])
        if not accessions:
            accessions.append({})
        accession = accessions[0]
        accession.setdefault("identifications", [])
        accession["identifications"] = [
            {"taxon": {"interpreted": "Pan"}},
            {"taxon": {"interpreted": "Gorilla"}},
        ]
        self.media.ocr_data = data
        self.media.save(update_fields=["ocr_data"])

    def build_post_data(self, **overrides):
        data = {
            "accession-collection": str(self.collection.pk),
            "accession-specimen_prefix": str(self.locality.pk),
            "accession-specimen_no": "123",
            "accession-type_status": "",
            "accession-comment": "",
            "accession-accessioned_by": str(self.expert.pk),
            "row-TOTAL_FORMS": "1",
            "row-INITIAL_FORMS": "1",
            "row-MIN_NUM_FORMS": "0",
            "row-MAX_NUM_FORMS": "1000",
            "row-0-row_id": "row-0",
            "row-0-order": "0",
            "row-0-specimen_suffix": "-",
            "row-0-storage": "",
            "row-0-status": InventoryStatus.UNKNOWN,
            "ident-TOTAL_FORMS": "1",
            "ident-INITIAL_FORMS": "1",
            "ident-MIN_NUM_FORMS": "0",
            "ident-MAX_NUM_FORMS": "1000",
            "ident-0-row_id": "row-0",
            "ident-0-taxon": "",
            "ident-0-identification_qualifier": "",
            "ident-0-identified_by": "",
            "ident-0-verbatim_identification": "",
            "ident-0-identification_remarks": "",
            "ident-0-reference": "",
            "ident-0-date_identified": "",
            "specimen-TOTAL_FORMS": "0",
            "specimen-INITIAL_FORMS": "0",
            "specimen-MIN_NUM_FORMS": "0",
            "specimen-MAX_NUM_FORMS": "1000",
            "reference-TOTAL_FORMS": "0",
            "reference-INITIAL_FORMS": "0",
            "reference-MIN_NUM_FORMS": "0",
            "reference-MAX_NUM_FORMS": "1000",
            "fieldslip-TOTAL_FORMS": "0",
            "fieldslip-INITIAL_FORMS": "0",
            "fieldslip-MIN_NUM_FORMS": "0",
            "fieldslip-MAX_NUM_FORMS": "1000",
        }
        data.update(overrides)
        return data

    def build_specimen_post_data(self, element=None, **overrides):
        base = self.build_post_data(
            **{
                "row-TOTAL_FORMS": "1",
                "row-INITIAL_FORMS": "1",
                "ident-TOTAL_FORMS": "1",
                "ident-INITIAL_FORMS": "1",
                "specimen-TOTAL_FORMS": "1",
                "specimen-INITIAL_FORMS": "1",
                "specimen-MIN_NUM_FORMS": "0",
                "specimen-MAX_NUM_FORMS": "1000",
                "specimen-0-row_id": "row-0",
                "specimen-0-side": "Left",
                "specimen-0-condition": "Excellent",
                "specimen-0-verbatim_element": "Left Femur",
                "specimen-0-portion": "Proximal",
                "specimen-0-fragments": "1",
            }
        )
        base["specimen-0-element"] = str(element.pk) if element else ""
        base.update(overrides)
        return base

    def get_url(self):
        return reverse("media_expert_qc", args=[self.media.uuid])

    def test_expert_can_approve_media(self):
        response = self.client.post(
            self.get_url(),
            self.build_post_data(action="approve", qc_comment="Looks good"),
        )
        self.assertRedirects(response, reverse("dashboard"))

        self.media.refresh_from_db()
        self.assertEqual(self.media.qc_status, Media.QCStatus.APPROVED)
        self.assertIsNotNone(self.media.accession)
        self.assertEqual(Accession.objects.count(), 1)
        comment = MediaQCComment.objects.get()
        self.assertIn("Looks good", comment.comment)

    def test_return_to_interns_creates_comment(self):
        response = self.client.post(
            self.get_url(),
            self.build_post_data(action="return_intern", qc_comment="Needs work"),
        )
        self.assertRedirects(response, reverse("dashboard"))

        self.media.refresh_from_db()
        self.assertEqual(self.media.qc_status, Media.QCStatus.PENDING_INTERN)
        comment = MediaQCComment.objects.get()
        self.assertIn("Needs work", comment.comment)

    def test_return_to_interns_visible_in_pending_queue(self):
        intern = get_user_model().objects.create_user(username="intern", password="pass")
        intern_group, _ = Group.objects.get_or_create(name="Interns")
        intern_group.user_set.add(intern)

        response = self.client.post(
            self.get_url(),
            self.build_post_data(action="return_intern", qc_comment="Needs work"),
        )
        self.assertRedirects(response, reverse("dashboard"))

        self.media.refresh_from_db()

        self.client.logout()
        self.client.force_login(intern)
        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Pending Intern Review")
        self.assertContains(response, self.media.file_name or self.media.media_location)
        self.assertContains(response, 'data-qc-status="pending_intern"')
        self.assertNotIn('data-qc-status="rejected"', response.content.decode())
        self.assertContains(response, "No media in this status.")

    def test_approve_creates_specimen_elements(self):
        element_parent = Element.objects.create(name="-Undefined")
        element = Element.objects.create(name="Femur", parent_element=element_parent)

        self.media.ocr_data = {
            "card_type": "accession_card",
            "accessions": [
                {
                    "collection_abbreviation": {"interpreted": "KNM"},
                    "specimen_prefix_abbreviation": {"interpreted": "AB"},
                    "specimen_no": {"interpreted": 123},
                    "rows": [
                        {
                            "_row_id": "row-0",
                            "specimen_suffix": {"interpreted": "A"},
                            "natures": [
                                {
                                    "element_name": {"interpreted": "Femur"},
                                    "side": {"interpreted": "Left"},
                                    "condition": {"interpreted": "Excellent"},
                                    "verbatim_element": {"interpreted": "Left Femur"},
                                    "portion": {"interpreted": "Proximal"},
                                    "fragments": {"interpreted": 1},
                                }
                            ],
                        }
                    ],
                    "identifications": [
                        {
                            "taxon": {"interpreted": "Homo"},
                            "verbatim_identification": {"interpreted": "Homo sp."},
                        }
                    ],
                }
            ],
        }
        self.media.save(update_fields=["ocr_data"])

        response = self.client.post(
            self.get_url(),
            self.build_specimen_post_data(
                element,
                action="approve",
                qc_comment="",
                **{
                    "row-0-row_id": "row-0",
                    "row-0-order": "0",
                    "row-0-specimen_suffix": "A",
                    "row-0-storage": "",
                    "row-0-status": InventoryStatus.UNKNOWN,
                    "ident-0-row_id": "row-0",
                    "ident-0-taxon": "Homo",
                    "ident-0-verbatim_identification": "Homo sp.",
                },
            ),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

        accession = Accession.objects.get()
        row = accession.accessionrow_set.get()
        nature = row.natureofspecimen_set.get()
        self.assertEqual(nature.element, element)
        self.assertEqual(nature.side, "Left")
        self.assertEqual(nature.condition, "Excellent")
        self.assertEqual(nature.verbatim_element, "Left Femur")
        self.assertEqual(nature.portion, "Proximal")
        self.assertEqual(nature.fragments, 1)

    def test_approve_with_verbatim_only_creates_specimen_element(self):
        parent = Element.objects.create(name="-Undefined")

        self.media.ocr_data = {
            "card_type": "accession_card",
            "accessions": [
                {
                    "collection_abbreviation": {"interpreted": "KNM"},
                    "specimen_prefix_abbreviation": {"interpreted": "AB"},
                    "specimen_no": {"interpreted": 123},
                    "rows": [
                        {
                            "_row_id": "row-0",
                            "specimen_suffix": {"interpreted": "A"},
                            "natures": [
                                {
                                    "element_name": {"interpreted": None},
                                    "side": {"interpreted": "Left"},
                                    "condition": {"interpreted": "Excellent"},
                                    "verbatim_element": {"interpreted": "Partial Femur"},
                                    "portion": {"interpreted": "Proximal"},
                                    "fragments": {"interpreted": 2},
                                }
                            ],
                        }
                    ],
                    "identifications": [
                        {
                            "taxon": {"interpreted": "Homo"},
                            "verbatim_identification": {"interpreted": "Homo sp."},
                        }
                    ],
                }
            ],
        }
        self.media.save(update_fields=["ocr_data"])

        response = self.client.post(
            self.get_url(),
            self.build_specimen_post_data(
                element=None,
                action="approve",
                qc_comment="",
                **{
                    "row-0-row_id": "row-0",
                    "row-0-order": "0",
                    "row-0-specimen_suffix": "A",
                    "row-0-storage": "",
                    "row-0-status": InventoryStatus.UNKNOWN,
                    "ident-0-row_id": "row-0",
                    "ident-0-taxon": "Homo",
                    "ident-0-verbatim_identification": "Homo sp.",
                    "specimen-0-verbatim_element": "Partial Femur",
                    "specimen-0-portion": "Proximal",
                    "specimen-0-fragments": "2",
                },
            ),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

        accession = Accession.objects.get()
        row = accession.accessionrow_set.get()
        nature = row.natureofspecimen_set.get()
        self.assertEqual(nature.element.name, "Partial Femur")
        self.assertEqual(nature.element.parent_element, parent)
        self.assertEqual(nature.verbatim_element, "Partial Femur")
        self.assertEqual(nature.fragments, 2)

    def test_request_rescan_sets_rejected_status(self):
        response = self.client.post(
            self.get_url(),
            self.build_post_data(action="request_rescan", qc_comment="Blurry"),
        )
        self.assertRedirects(response, reverse("dashboard"))

        self.media.refresh_from_db()
        self.assertEqual(self.media.qc_status, Media.QCStatus.REJECTED)
        comment = MediaQCComment.objects.get()
        self.assertIn("Blurry", comment.comment)

    def test_save_and_continue_does_not_change_status(self):
        response = self.client.post(
            self.get_url(),
            self.build_post_data(action="save", qc_comment=""),
        )
        self.assertRedirects(response, self.get_url())

        self.media.refresh_from_db()
        self.assertEqual(self.media.qc_status, Media.QCStatus.PENDING_EXPERT)
        self.assertEqual(MediaQCComment.objects.count(), 0)

    def test_approval_blocked_when_warnings_unacknowledged(self):
        self.add_unlinked_identification_warning()

        response = self.client.post(
            self.get_url(),
            self.build_post_data(action="approve", qc_comment="Review"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "identification record",
        )

        self.media.refresh_from_db()
        self.assertEqual(self.media.qc_status, Media.QCStatus.PENDING_EXPERT)
        self.assertFalse(
            MediaQCLog.objects.filter(
                media=self.media, field_name="warning_acknowledged"
            ).exists()
        )

    def test_acknowledged_warning_is_logged_on_approval(self):
        self.add_unlinked_identification_warning()

        post_data = self.build_post_data(
            action="approve", qc_comment="Warnings reviewed"
        )
        post_data.setdefault("acknowledge_warnings", [])
        post_data["acknowledge_warnings"].append("unlinked_identifications")

        response = self.client.post(self.get_url(), post_data)

        self.assertRedirects(response, reverse("dashboard"))

        self.media.refresh_from_db()
        self.assertEqual(self.media.qc_status, Media.QCStatus.APPROVED)

        log_entry = MediaQCLog.objects.filter(
            media=self.media, field_name="warning_acknowledged"
        ).get()
        self.assertEqual(log_entry.change_type, MediaQCLog.ChangeType.OCR_DATA)
        self.assertEqual(log_entry.old_value.get("code"), "unlinked_identifications")
        self.assertTrue(log_entry.new_value.get("acknowledged"))
        self.assertEqual(log_entry.new_value.get("count"), 1)

    def test_approval_blocked_when_accession_exists(self):
        accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=123,
            instance_number=1,
        )
        self.media.accession = accession
        self.media.save(update_fields=["accession"])

        response = self.client.post(
            self.get_url(),
            self.build_post_data(action="approve", qc_comment="Retry"),
        )
        self.assertEqual(response.status_code, 200)

        self.media.refresh_from_db()
        self.assertEqual(self.media.qc_status, Media.QCStatus.PENDING_EXPERT)
        self.assertEqual(MediaQCComment.objects.count(), 0)

    def test_importer_exception_surfaces_error(self):
        with patch(
            "cms.ocr_processing.create_accessions_from_media",
            side_effect=RuntimeError("Importer failed"),
        ):
            response = self.client.post(
                self.get_url(),
                self.build_post_data(action="approve", qc_comment="Approve"),
            )
        self.assertEqual(response.status_code, 200)

        self.media.refresh_from_db()
        self.assertEqual(self.media.qc_status, Media.QCStatus.PENDING_EXPERT)
        self.assertEqual(MediaQCComment.objects.count(), 0)

    def test_duplicate_requires_resolution(self):
        Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=123,
        )
        response = self.client.post(
            self.get_url(),
            self.build_post_data(action="approve", qc_comment="Approve"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select how to handle the existing accession")
        self.media.refresh_from_db()
        self.assertEqual(self.media.qc_status, Media.QCStatus.PENDING_EXPERT)

    def test_duplicate_create_new_instance(self):
        Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=123,
        )
        conflicts = describe_accession_conflicts(self.media)
        html_key = conflicts[0]["html_key"]
        post_data = self.build_post_data(action="approve", qc_comment="Approve")
        post_data.update({
            f"resolution_action__{html_key}": "new_instance",
        })
        response = self.client.post(self.get_url(), post_data)
        self.assertRedirects(response, reverse("dashboard"))

        media = Media.objects.get(pk=self.media.pk)
        self.assertEqual(media.qc_status, Media.QCStatus.APPROVED)
        accessions = Accession.objects.filter(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=123,
        ).order_by("instance_number")
        self.assertEqual(accessions.count(), 2)
        self.assertEqual(media.accession, accessions.last())

    def test_duplicate_update_existing(self):
        accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=123,
            comment="Original",
        )
        AccessionRow.objects.create(accession=accession, specimen_suffix="-")
        self.media.ocr_data = {
            "card_type": "accession_card",
            "accessions": [
                {
                    "collection_abbreviation": {"interpreted": "KNM"},
                    "specimen_prefix_abbreviation": {"interpreted": "AB"},
                    "specimen_no": {"interpreted": 123},
                    "additional_notes": [
                        {
                            "heading": {"interpreted": "Note"},
                            "value": {"interpreted": "Updated guidance"},
                        }
                    ],
                    "rows": [
                        {
                            "specimen_suffix": {"interpreted": "-"},
                            "storage_area": {"interpreted": "Shelf 42"},
                        }
                    ],
                }
            ],
        }
        self.media.save(update_fields=["ocr_data"])

        conflicts = describe_accession_conflicts(self.media)
        html_key = conflicts[0]["html_key"]
        row_suffix = conflicts[0]["proposed"]["rows"][0]["html_suffix"]
        post_data = self.build_post_data(action="approve", qc_comment="Approve")
        post_data.update(
            {
                f"resolution_action__{html_key}": "update_existing",
                f"target_accession__{html_key}": str(accession.pk),
                f"apply_field__{html_key}__comment": "on",
                f"replace_row__{html_key}__{row_suffix}": "on",
            }
        )

        response = self.client.post(self.get_url(), post_data)
        self.assertRedirects(response, reverse("dashboard"))

        accession.refresh_from_db()
        media = Media.objects.get(pk=self.media.pk)
        self.assertEqual(media.qc_status, Media.QCStatus.APPROVED)
        self.assertEqual(media.accession, accession)
        self.assertEqual(accession.comment, "Note: Updated guidance")
        row = accession.accessionrow_set.get(specimen_suffix="-")
        self.assertEqual(row.storage.area, "Shelf 42")

    def test_initial_rows_copy_missing_identifications_and_specimens(self):
        Element.objects.create(name="Femur")
        self.media.ocr_data = {
            "card_type": "accession_card",
            "accessions": [
                {
                    "collection_abbreviation": {"interpreted": "KNM"},
                    "specimen_prefix_abbreviation": {"interpreted": "AB"},
                    "specimen_no": {"interpreted": 123},
                    "rows": [
                        {
                            "_row_id": "row-0",
                            "specimen_suffix": {"interpreted": "A"},
                            "natures": [
                                {
                                    "element_name": {"interpreted": "Femur"},
                                    "verbatim_element": {"interpreted": "Femur"},
                                    "portion": {"interpreted": "Proximal"},
                                }
                            ],
                        },
                        {
                            "_row_id": "row-1",
                            "specimen_suffix": {"interpreted": "B"},
                            "natures": [],
                        },
                        {
                            "_row_id": "row-2",
                            "specimen_suffix": {"interpreted": "C"},
                            "natures": [],
                        },
                    ],
                    "identifications": [
                        {
                            "taxon": {"interpreted": "Homo"},
                            "verbatim_identification": {"interpreted": "Homo sp."},
                        }
                    ],
                }
            ],
        }
        self.media.save(update_fields=["ocr_data"])

        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)
        row_contexts = response.context["row_contexts"]
        self.assertEqual(len(row_contexts), 3)
        for context in row_contexts:
            ident_forms = context["ident_forms"]
            self.assertEqual(len(ident_forms), 1)
            self.assertEqual(ident_forms[0]["taxon"].value(), "Homo")
            specimen_forms = context["specimen_forms"]
            self.assertEqual(len(specimen_forms), 1)
            self.assertEqual(specimen_forms[0]["verbatim_element"].value(), "Femur")

    def test_non_expert_forbidden(self):
        User = get_user_model()
        other = User.objects.create_user(username="visitor", password="pass")
        self.client.logout()
        self.client.force_login(other)

        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 403)


class StorageViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.manager = User.objects.create_user(username="manager", password="pass")
        self.observer = User.objects.create_user(username="observer", password="pass")

        self.patcher = patch("cms.models.get_current_user", return_value=self.manager)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.collection = Collection.objects.create(
            abbreviation="COL", description="Collection"
        )
        self.locality = Locality.objects.create(abbreviation="LC", name="Locality")

        self.cm_group = Group.objects.create(name="Collection Managers")
        self.cm_group.user_set.add(self.manager)

    def create_storage_with_specimen(self):
        parent = Storage.objects.create(area="Room A")
        Storage.objects.create(area="Shelf 1", parent_area=parent)
        accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
            accessioned_by=self.manager,
        )
        AccessionRow.objects.create(
            accession=accession,
            storage=parent,
            specimen_suffix="A",
        )
        return parent

    def test_storage_list_requires_collection_manager(self):
        self.client.login(username="observer", password="pass")
        response = self.client.get(reverse("storage_list"))
        self.assertEqual(response.status_code, 403)

    def test_storage_list_shows_counts_for_authorised_user(self):
        self.create_storage_with_specimen()
        self.client.login(username="manager", password="pass")
        response = self.client.get(reverse("storage_list"))
        self.assertEqual(response.status_code, 200)
        storages = list(response.context["storages"])
        self.assertGreaterEqual(len(storages), 2)
        parent_entry = next(s for s in storages if s.area == "Room A")
        self.assertEqual(parent_entry.specimen_count, 1)
        self.assertEqual(len(parent_entry.storage_set.all()), 1)

    def test_storage_detail_lists_children_and_specimens(self):
        parent = self.create_storage_with_specimen()
        self.client.login(username="manager", password="pass")
        response = self.client.get(reverse("storage_detail", args=[parent.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["children"]), 1)
        self.assertEqual(len(response.context["specimens"]), 1)

    def test_storage_create_creates_record(self):
        self.client.login(username="manager", password="pass")
        response = self.client.post(
            reverse("storage_create"),
            {"area": "New Storage", "parent_area": ""},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Storage.objects.filter(area="New Storage").exists())


class MediaFileDeletionTests(TestCase):
    """Ensure deleting a Media record removes its file from disk."""

    def setUp(self):
        import shutil

        User = get_user_model()
        self.user = User.objects.create_user(username="deleter", password="pass")
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.uploads = Path(settings.MEDIA_ROOT) / "uploads"
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.uploads, ignore_errors=True))

    def test_file_removed_on_delete(self):
        file_path = self.uploads / "deleteme.png"
        file_path.write_bytes(b"data")
        media = Media.objects.create(media_location="uploads/deleteme.png")
        self.assertTrue(file_path.exists())
        media.delete()
        self.assertFalse(file_path.exists())


class ApplyRowsFallbackTests(TestCase):
    def setUp(self):
        self.collection = Collection.objects.create(
            abbreviation="KNM", description="Kenya"
        )
        self.locality = Locality.objects.create(abbreviation="AB", name="Area")
        self.accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=100,
            instance_number=1,
        )

    def test_reuses_last_identification_and_specimens_for_missing_rows(self):
        rows = [
            {
                "specimen_suffix": "-",
                "storage": None,
                "identification": {
                    "taxon": "Homo sp.",
                    "verbatim_identification": "Homo sp.",
                },
                "natures": [
                    {
                        "element_name": "Femur",
                        "verbatim_element": "Femur",
                        "portion": "Proximal",
                        "fragments": 1,
                    }
                ],
            },
            {
                "specimen_suffix": "A",
                "storage": None,
                "identification": {},
                "natures": [],
            },
            {
                "specimen_suffix": "B",
                "storage": None,
                "identification": {},
                "natures": [],
            },
        ]

        _apply_rows(self.accession, rows)

        for suffix in ("-", "A", "B"):
            row = self.accession.accessionrow_set.get(specimen_suffix=suffix)
            ident = row.identification_set.get()
            self.assertEqual(ident.taxon, "Homo sp.")
            specimen = row.natureofspecimen_set.get()
            self.assertEqual(specimen.element.name, "Femur")
            self.assertEqual(specimen.portion, "Proximal")


class MediaQCHistoryViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="staff", password="pass", is_staff=True
        )
        self.other = User.objects.create_user(username="viewer", password="pass")

        patcher = patch("cms.models.get_current_user", return_value=self.staff)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.media = Media.objects.create(
            media_location="uploads/history.png",
            file_name="history.png",
        )
        self.log = MediaQCLog.objects.create(
            media=self.media,
            change_type=MediaQCLog.ChangeType.STATUS,
            field_name="qc_status",
            old_value={"qc_status": Media.QCStatus.PENDING_INTERN},
            new_value={"qc_status": Media.QCStatus.PENDING_EXPERT},
            description="Status advanced to expert review.",
            changed_by=self.staff,
        )
        self.comment = MediaQCComment.objects.create(
            log=self.log,
            comment="Looks good.",
            created_by=self.staff,
        )

    def test_requires_staff_user(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("media_qc_history"))
        self.assertEqual(response.status_code, 403)

    def test_staff_can_view_history(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("media_qc_history"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Status advanced to expert review.")
        self.assertContains(response, "Looks good.")
        self.assertIn(self.log, list(response.context["page_obj"].object_list))

    def test_history_can_filter_by_media(self):
        other_media = Media.objects.create(media_location="uploads/other.png")
        MediaQCLog.objects.create(
            media=other_media,
            change_type=MediaQCLog.ChangeType.STATUS,
            field_name="qc_status",
            new_value={"qc_status": Media.QCStatus.PENDING_INTERN},
            changed_by=self.staff,
        )

        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("media_qc_history"), {"media": str(self.media.uuid)}
        )
        self.assertEqual(response.status_code, 200)
        page_logs = list(response.context["page_obj"].object_list)
        self.assertEqual(page_logs, [self.log])
        self.assertEqual(response.context["filter_media"], self.media)


class MediaInternQCWizardTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.intern = User.objects.create_user(username="intern", password="pass")
        self.other_user = User.objects.create_user(username="user", password="pass")
        intern_group, _ = Group.objects.get_or_create(name="Interns")
        intern_group.user_set.add(self.intern)
        patcher = patch("cms.models.get_current_user", return_value=self.intern)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.collection = Collection.objects.create(abbreviation="KNM", description="Kenya")
        self.locality = Locality.objects.create(abbreviation="AB", name="Area B")
        self.storage1 = Storage.objects.create(area="Cabinet 1")
        self.storage2 = Storage.objects.create(area="Cabinet 2")
        self.storage3 = Storage.objects.create(area="Cabinet 3")
        self.element = Element.objects.create(name="Femur")

        self.media = Media.objects.create(
            media_location="uploads/pending/test.png",
            ocr_data={
                "card_type": "accession_card",
                "accessions": [
                    {
                        "collection_abbreviation": {"interpreted": "KNM"},
                        "specimen_prefix_abbreviation": {"interpreted": "AB"},
                        "specimen_no": {"interpreted": 100},
                        "type_status": {"interpreted": "Holotype"},
                        "comment": {"interpreted": "Initial"},
                        "rows": [
                            {
                                "specimen_suffix": {"interpreted": "A"},
                                "storage_area": {"interpreted": "Cabinet 1"},
                                "natures": [
                                    {
                                        "element_name": {"interpreted": "Femur"},
                                        "side": {"interpreted": "Left"},
                                        "condition": {"interpreted": "Good"},
                                        "verbatim_element": {"interpreted": "Femur"},
                                        "portion": {"interpreted": "Proximal"},
                                        "fragments": {"interpreted": 1},
                                    }
                                ],
                            },
                            {
                                "specimen_suffix": {"interpreted": "B"},
                                "storage_area": {"interpreted": "Cabinet 2"},
                                "natures": [],
                            },
                        ],
                        "references": [
                            {
                                "reference_first_author": {"interpreted": "Harris"},
                                "reference_title": {"interpreted": "Lothagam"},
                                "reference_year": {"interpreted": "2003"},
                                "page": {"interpreted": "485-519"},
                            }
                        ],
                        "field_slips": [
                            {
                                "field_number": {"interpreted": "FS-1"},
                                "verbatim_locality": {"interpreted": "Loc1"},
                                "verbatim_taxon": {"interpreted": "Homo"},
                                "verbatim_element": {"interpreted": "Femur"},
                                "verbatim_horizon": {
                                    "formation": {"interpreted": "Form"},
                                    "member": {"interpreted": "Member"},
                                    "bed_or_horizon": {"interpreted": "Bed"},
                                    "chronostratigraphy": {"interpreted": "Zone"},
                                },
                                "aerial_photo": {"interpreted": "Photo 1"},
                                "verbatim_latitude": {"interpreted": "Lat"},
                                "verbatim_longitude": {"interpreted": "Lon"},
                                "verbatim_elevation": {"interpreted": "100"},
                            }
                        ],
                        "identifications": [
                            {
                                "taxon": {"interpreted": "Homo"},
                                "identification_qualifier": {"interpreted": "cf."},
                                "verbatim_identification": {"interpreted": "Homo cf. habilis"},
                                "identification_remarks": {"interpreted": "Remark"},
                            },
                            {},
                        ],
                    }
                ],
            },
        )

    def get_url(self):
        return reverse("media_intern_qc", args=[str(self.media.uuid)])

    def build_valid_post_data(self):
        return {
            "accession-collection": str(self.collection.pk),
            "accession-specimen_prefix": str(self.locality.pk),
            "accession-specimen_no": "101",
            "accession-type_status": "Holotype",
            "accession-comment": "Updated",
            "accession-accessioned_by": str(self.intern.pk),
            "row-TOTAL_FORMS": "2",
            "row-INITIAL_FORMS": "2",
            "row-MIN_NUM_FORMS": "0",
            "row-MAX_NUM_FORMS": "1000",
            "row-0-row_id": "row-0",
            "row-0-order": "1",
            "row-0-specimen_suffix": "A",
            "row-0-storage": "Cabinet 3",
            "row-0-status": InventoryStatus.UNKNOWN,
            "row-1-row_id": "row-1",
            "row-1-order": "0",
            "row-1-specimen_suffix": "B",
            "row-1-storage": "Cabinet 2",
            "row-1-status": InventoryStatus.UNKNOWN,
            "ident-TOTAL_FORMS": "2",
            "ident-INITIAL_FORMS": "2",
            "ident-MIN_NUM_FORMS": "0",
            "ident-MAX_NUM_FORMS": "1000",
            "ident-0-row_id": "row-0",
            "ident-0-taxon": "Pan",
            "ident-0-identification_qualifier": "cf.",
            "ident-0-identified_by": "",
            "ident-0-verbatim_identification": "Pan cf. troglodytes",
            "ident-0-identification_remarks": "Revised",
            "ident-0-reference": "",
            "ident-0-date_identified": "",
            "ident-1-row_id": "row-1",
            "ident-1-taxon": "",
            "ident-1-identification_qualifier": "",
            "ident-1-identified_by": "",
            "ident-1-verbatim_identification": "",
            "ident-1-identification_remarks": "",
            "ident-1-reference": "",
            "ident-1-date_identified": "",
            "specimen-TOTAL_FORMS": "2",
            "specimen-INITIAL_FORMS": "2",
            "specimen-MIN_NUM_FORMS": "0",
            "specimen-MAX_NUM_FORMS": "1000",
            "specimen-0-row_id": "row-0",
            "specimen-0-element": str(self.element.pk),
            "specimen-0-side": "Left",
            "specimen-0-condition": "Excellent",
            "specimen-0-verbatim_element": "Femur",
            "specimen-0-portion": "Proximal",
            "specimen-0-fragments": "3",
            "specimen-1-row_id": "row-1",
            "specimen-1-element": str(self.element.pk),
            "specimen-1-side": "Left",
            "specimen-1-condition": "Excellent",
            "specimen-1-verbatim_element": "Femur",
            "specimen-1-portion": "Proximal",
            "specimen-1-fragments": "3",
            "reference-TOTAL_FORMS": "1",
            "reference-INITIAL_FORMS": "1",
            "reference-MIN_NUM_FORMS": "0",
            "reference-MAX_NUM_FORMS": "1000",
            "reference-0-ref_id": "ref-0",
            "reference-0-order": "0",
            "reference-0-first_author": "Leakey",
            "reference-0-title": "Koobi Fora",
            "reference-0-year": "2004",
            "reference-0-page": "120-135",
            "fieldslip-TOTAL_FORMS": "1",
            "fieldslip-INITIAL_FORMS": "1",
            "fieldslip-MIN_NUM_FORMS": "0",
            "fieldslip-MAX_NUM_FORMS": "1000",
            "fieldslip-0-slip_id": "field-slip-0",
            "fieldslip-0-order": "0",
            "fieldslip-0-field_number": "FS-2",
            "fieldslip-0-verbatim_locality": "Loc2",
            "fieldslip-0-verbatim_taxon": "Pan",
            "fieldslip-0-verbatim_element": "Tooth",
            "fieldslip-0-horizon_formation": "NewForm",
            "fieldslip-0-horizon_member": "NewMember",
            "fieldslip-0-horizon_bed": "NewBed",
            "fieldslip-0-horizon_chronostratigraphy": "NewZone",
            "fieldslip-0-aerial_photo": "Photo 2",
            "fieldslip-0-verbatim_latitude": "Lat2",
            "fieldslip-0-verbatim_longitude": "Lon2",
            "fieldslip-0-verbatim_elevation": "200",
        }

    def test_non_intern_forbidden(self):
        self.client.login(username="user", password="pass")
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 403)

    def test_get_prefills_forms(self):
        self.client.login(username="intern", password="pass")
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)
        accession_form = response.context["accession_form"]
        row_contexts = response.context.get("row_contexts")
        self.assertEqual(len(row_contexts), 2)
        self.assertEqual(accession_form["specimen_no"].value(), "100")
        self.assertNotIn("readonly", accession_form.fields["specimen_no"].widget.attrs)
        reference_forms = response.context["reference_formset"].forms
        self.assertEqual(len(reference_forms), 1)
        self.assertEqual(reference_forms[0]["first_author"].value(), "Harris")
        fieldslip_forms = response.context["fieldslip_formset"].forms
        self.assertEqual(len(fieldslip_forms), 1)
        self.assertEqual(fieldslip_forms[0]["field_number"].value(), "FS-1")

    def test_context_includes_recent_history(self):
        log = MediaQCLog.objects.create(
            media=self.media,
            change_type=MediaQCLog.ChangeType.STATUS,
            field_name="qc_status",
            old_value={"qc_status": Media.QCStatus.PENDING_INTERN},
            new_value={"qc_status": Media.QCStatus.PENDING_EXPERT},
            description="Escalated for expert review.",
            changed_by=self.intern,
        )
        MediaQCComment.objects.create(
            log=log,
            comment="Please double-check storage.",
            created_by=self.intern,
        )

        self.client.login(username="intern", password="pass")
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)
        history = response.context["qc_history_logs"]
        self.assertTrue(history)
        self.assertEqual(history[0], log)
        comments = list(history[0].comments.all())
        self.assertEqual(comments[0].comment, "Please double-check storage.")

    def test_post_updates_media_and_logs(self):
        self.client.login(username="intern", password="pass")
        url = self.get_url()
        data = self.build_valid_post_data()

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.media.refresh_from_db()
        accession_payload = self.media.ocr_data["accessions"][0]
        self.assertEqual(accession_payload["specimen_no"]["interpreted"], 101)
        rows = accession_payload["rows"]
        self.assertEqual(rows[0]["specimen_suffix"]["interpreted"], "B")
        self.assertEqual(rows[1]["specimen_suffix"]["interpreted"], "A")
        self.assertEqual(rows[1]["storage_area"]["interpreted"], "Cabinet 3")
        identifications = accession_payload["identifications"]
        self.assertEqual(identifications[1]["taxon"]["interpreted"], "Pan")
        references = accession_payload["references"]
        self.assertEqual(references[0]["reference_first_author"]["interpreted"], "Leakey")
        self.assertEqual(references[0]["page"]["interpreted"], "120-135")
        field_slips = accession_payload["field_slips"]
        self.assertEqual(field_slips[0]["field_number"]["interpreted"], "FS-2")
        self.assertEqual(
            field_slips[0]["verbatim_horizon"]["formation"]["interpreted"],
            "NewForm",
        )

        self.assertTrue(self.media.rows_rearranged)
        self.assertEqual(self.media.qc_status, Media.QCStatus.PENDING_EXPERT)
        self.assertEqual(self.media.intern_checked_by, self.intern)

        ocr_logs = MediaQCLog.objects.filter(
            media=self.media, change_type=MediaQCLog.ChangeType.OCR_DATA
        )
        self.assertTrue(ocr_logs.exists())
        self.assertTrue(
            ocr_logs.filter(field_name="accessions[0].specimen_no").exists()
        )
        self.assertTrue(
            ocr_logs.filter(
                field_name="accessions[0].references[0].reference_first_author"
            ).exists()
        )
        self.assertTrue(
            ocr_logs.filter(
                field_name="accessions[0].field_slips[0].field_number"
            ).exists()
        )

    def test_accepts_new_storage_value(self):
        self.client.login(username="intern", password="pass")
        url = self.get_url()
        data = self.build_valid_post_data()
        data["row-0-storage"] = "Shelf 42"

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.media.refresh_from_db()
        rows = self.media.ocr_data["accessions"][0]["rows"]
        self.assertEqual(rows[1]["storage_area"]["interpreted"], "Shelf 42")
        self.assertTrue(Storage.objects.filter(area="Shelf 42").exists())

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Shelf 42", response.context["storage_suggestions"])

    def test_can_add_reference_entry(self):
        self.client.login(username="intern", password="pass")
        url = self.get_url()
        data = self.build_valid_post_data()
        data.update(
            {
                "reference-TOTAL_FORMS": "3",
                "reference-1-ref_id": "",
                "reference-1-order": "1",
                "reference-1-first_author": "New Author",
                "reference-1-title": "New Insights",
                "reference-1-year": "2020",
                "reference-1-page": "10-12",
                "reference-2-ref_id": "",
                "reference-2-order": "2",
                "reference-2-first_author": "  ",
                "reference-2-title": "",
                "reference-2-year": "",
                "reference-2-page": "",
            }
        )

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.media.refresh_from_db()
        references = self.media.ocr_data["accessions"][0]["references"]
        self.assertEqual(len(references), 2)
        self.assertEqual(
            references[1]["reference_first_author"]["interpreted"], "New Author"
        )
        self.assertEqual(references[1]["page"]["interpreted"], "10-12")

    def test_handles_inserted_row_payload(self):
        self.client.login(username="intern", password="pass")
        url = self.get_url()
        data = self.build_valid_post_data()
        data.update(
            {
                "row-TOTAL_FORMS": "3",
                "row-2-row_id": "row-2",
                "row-2-order": "2",
                "row-2-specimen_suffix": "C",
                "row-2-storage": "Cabinet 4",
                "row-2-status": InventoryStatus.UNKNOWN,
                "specimen-TOTAL_FORMS": "2",
                "specimen-INITIAL_FORMS": "1",
                "specimen-1-row_id": "row-2",
                "specimen-1-element": str(self.element.pk),
                "specimen-1-side": "Right",
                "specimen-1-condition": "Good",
                "specimen-1-verbatim_element": "Femur",
                "specimen-1-portion": "Distal",
                "specimen-1-fragments": "1",
            }
        )

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.media.refresh_from_db()
        rows = self.media.ocr_data["accessions"][0]["rows"]
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[2]["specimen_suffix"]["interpreted"], "C")
        self.assertEqual(rows[2]["storage_area"]["interpreted"], "Cabinet 4")
        natures = rows[2]["natures"]
        self.assertEqual(len(natures), 1)
        self.assertEqual(natures[0]["element_name"]["interpreted"], "Femur")
        self.assertEqual(natures[0]["portion"]["interpreted"], "Distal")

    def test_handles_added_specimen_payload(self):
        self.client.login(username="intern", password="pass")
        url = self.get_url()
        data = self.build_valid_post_data()
        data.update(
            {
                "specimen-TOTAL_FORMS": "2",
                "specimen-1-row_id": "row-1",
                "specimen-1-element": str(self.element.pk),
                "specimen-1-side": "Right",
                "specimen-1-condition": "Fair",
                "specimen-1-verbatim_element": "Mandible fragment",
                "specimen-1-portion": "Complete",
                "specimen-1-fragments": "2",
            }
        )

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.media.refresh_from_db()
        accession_payload = self.media.ocr_data["accessions"][0]
        rows = accession_payload["rows"]
        target_row = next(
            row for row in rows if row["specimen_suffix"]["interpreted"] == "B"
        )
        self.assertEqual(len(target_row["natures"]), 1)
        added_nature = target_row["natures"][0]
        self.assertEqual(added_nature["element_name"]["interpreted"], "Femur")
        self.assertEqual(added_nature["side"]["interpreted"], "Right")
        self.assertEqual(added_nature["portion"]["interpreted"], "Complete")

    def test_handles_ident_update_on_existing_row(self):
        """Interns can edit the default identification chip on an existing row."""

        self.client.login(username="intern", password="pass")
        url = self.get_url()
        data = self.build_valid_post_data()
        data.update(
            {
                "ident-1-taxon": "Homo",
                "ident-1-identification_qualifier": "cf.",
                "ident-1-verbatim_identification": "Homo cf.",
                "ident-1-identification_remarks": "Updated during QC",
            }
        )

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.media.refresh_from_db()
        accession_payload = self.media.ocr_data["accessions"][0]
        rows = accession_payload["rows"]
        identifications = accession_payload["identifications"]
        suffixes = [row["specimen_suffix"]["interpreted"] for row in rows]
        updated_index = suffixes.index("B")
        updated_ident = identifications[updated_index]
        self.assertEqual(updated_ident["taxon"]["interpreted"], "Homo")
        self.assertEqual(
            updated_ident["identification_qualifier"]["interpreted"], "cf."
        )
        self.assertEqual(
            updated_ident["identification_remarks"]["interpreted"],
            "Updated during QC",
        )

    def test_handles_new_identification_for_added_row(self):
        self.client.login(username="intern", password="pass")
        url = self.get_url()
        data = self.build_valid_post_data()
        data.update(
            {
                "row-TOTAL_FORMS": "3",
                "row-2-row_id": "row-2",
                "row-2-order": "2",
                "row-2-specimen_suffix": "C",
                "row-2-storage": "Drawer 15",
                "row-2-status": InventoryStatus.UNKNOWN,
                "specimen-TOTAL_FORMS": "2",
                "specimen-1-row_id": "row-2",
                "specimen-1-element": str(self.element.pk),
                "specimen-1-side": "Left",
                "specimen-1-condition": "Good",
                "specimen-1-verbatim_element": "Tooth",
                "specimen-1-portion": "Crown",
                "specimen-1-fragments": "1",
                "ident-TOTAL_FORMS": "3",
                "ident-2-row_id": "row-2",
                "ident-2-taxon": "Papio",
                "ident-2-identification_qualifier": "cf.",
                "ident-2-identified_by": "",
                "ident-2-verbatim_identification": "Papio cf.",
                "ident-2-identification_remarks": "Added manually",
                "ident-2-reference": "",
                "ident-2-date_identified": "",
            }
        )

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.media.refresh_from_db()
        accession_payload = self.media.ocr_data["accessions"][0]
        rows = accession_payload["rows"]
        identifications = accession_payload["identifications"]
        suffixes = [row["specimen_suffix"]["interpreted"] for row in rows]
        self.assertEqual(len(suffixes), len(identifications))
        new_index = suffixes.index("C")
        self.assertEqual(
            identifications[new_index]["taxon"]["interpreted"], "Papio"
        )
        self.assertEqual(
            identifications[new_index]["identification_qualifier"]["interpreted"],
            "cf.",
        )

    def test_handles_deleted_identification_payload(self):
        self.client.login(username="intern", password="pass")
        url = self.get_url()
        data = self.build_valid_post_data()
        data["ident-0-DELETE"] = "on"

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.media.refresh_from_db()
        accession_payload = self.media.ocr_data["accessions"][0]
        rows = accession_payload["rows"]
        identifications = accession_payload["identifications"]
        suffixes = [row["specimen_suffix"]["interpreted"] for row in rows]
        self.assertEqual(len(suffixes), len(identifications))
        deleted_index = suffixes.index("A")
        cleared_ident = identifications[deleted_index]
        self.assertIsNone(cleared_ident["taxon"]["interpreted"])
        self.assertIsNone(
            cleared_ident["identification_qualifier"]["interpreted"]
        )
        self.assertIsNone(
            cleared_ident["identification_remarks"]["interpreted"]
        )

    def test_handles_deleted_specimen_payload(self):
        """Specimen chips flagged for deletion are removed from the payload."""

        self.client.login(username="intern", password="pass")
        url = self.get_url()
        data = self.build_valid_post_data()
        data["specimen-0-DELETE"] = "on"

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.media.refresh_from_db()
        accession_payload = self.media.ocr_data["accessions"][0]
        rows = accession_payload["rows"]
        identifications = accession_payload["identifications"]
        suffixes = [row["specimen_suffix"]["interpreted"] for row in rows]
        leading_index = suffixes.index("A")
        leading_row = rows[leading_index]
        leading_ident = identifications[leading_index]
        self.assertEqual(leading_row["natures"], [])
        # Identification remains intact after removing the specimen chip.
        self.assertEqual(leading_ident["taxon"]["interpreted"], "Pan")

    def test_handles_split_payload_creates_new_row(self):
        self.client.login(username="intern", password="pass")
        url = self.get_url()
        data = self.build_valid_post_data()
        data.update(
            {
                "row-TOTAL_FORMS": "3",
                "row-2-row_id": "row-2",
                "row-2-order": "2",
                "row-2-specimen_suffix": "C",
                "row-2-storage": "Drawer 10",
                "row-2-status": InventoryStatus.UNKNOWN,
            }
        )
        data["specimen-0-row_id"] = "row-2"

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.media.refresh_from_db()
        accession_payload = self.media.ocr_data["accessions"][0]
        rows = accession_payload["rows"]
        self.assertEqual(len(rows), 3)
        moved_row = rows[2]
        self.assertEqual(moved_row["storage_area"]["interpreted"], "Drawer 10")
        self.assertEqual(len(moved_row["natures"]), 1)
        original_first_row = rows[1]
        self.assertEqual(original_first_row["natures"], [])

    def test_handles_merged_rows_payload(self):
        self.client.login(username="intern", password="pass")
        url = self.get_url()
        data = self.build_valid_post_data()
        for key in list(data.keys()):
            if key.startswith("row-1-"):
                data.pop(key)
            if key.startswith("ident-1-"):
                data.pop(key)
        data.update(
            {
                "row-TOTAL_FORMS": "1",
                "row-INITIAL_FORMS": "1",
                "ident-TOTAL_FORMS": "1",
                "ident-INITIAL_FORMS": "1",
            }
        )

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.media.refresh_from_db()
        rows = self.media.ocr_data["accessions"][0]["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["specimen_suffix"]["interpreted"], "A")

    def test_does_not_create_storage_when_submission_invalid(self):
        self.client.login(username="intern", password="pass")
        url = self.get_url()
        data = self.build_valid_post_data()
        data["row-0-storage"] = "Drawer 99"
        data["row-0-specimen_suffix"] = "InvalidSuffix"

        self.assertFalse(Storage.objects.filter(area="Drawer 99").exists())

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        self.assertFalse(Storage.objects.filter(area="Drawer 99").exists())

    def test_displays_expert_comments_when_present(self):
        expert = get_user_model().objects.create_user(username="expert", password="pass")
        old_log = MediaQCLog.objects.create(
            media=self.media,
            change_type=MediaQCLog.ChangeType.STATUS,
            field_name="qc_status",
            old_value={"qc_status": Media.QCStatus.PENDING_EXPERT},
            new_value={"qc_status": Media.QCStatus.PENDING_INTERN},
            description="Initial return",
            changed_by=expert,
        )
        MediaQCComment.objects.create(
            log=old_log,
            comment="First round of feedback",
            created_by=expert,
        )
        new_log = MediaQCLog.objects.create(
            media=self.media,
            change_type=MediaQCLog.ChangeType.STATUS,
            field_name="qc_status",
            old_value={"qc_status": Media.QCStatus.PENDING_EXPERT},
            new_value={"qc_status": Media.QCStatus.PENDING_INTERN},
            description="Follow-up",
            changed_by=expert,
        )
        MediaQCComment.objects.create(
            log=new_log,
            comment="Please double-check the specimen storage",
            created_by=expert,
        )

        self.client.login(username="intern", password="pass")
        response = self.client.get(self.get_url())

        self.assertContains(response, "Expert Feedback")
        self.assertContains(response, "Latest reviewer comment")
        self.assertContains(response, "Please double-check the specimen storage")
        self.assertContains(response, "Earlier comments")
        self.assertContains(response, "First round of feedback")
        self.assertContains(response, expert.username)


class LLMUsageRecordQuerySetTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="usage", password="pass")
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_for_media_and_totals_by_day(self):
        media_one = Media.objects.create(media_location="uploads/ocr/one.png")
        media_two = Media.objects.create(media_location="uploads/ocr/two.png")

        record_one = LLMUsageRecord.objects.create(
            media=media_one,
            model_name="gpt-4o",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            cost_usd=Decimal("0.123456"),
        )
        record_two = LLMUsageRecord.objects.create(
            media=media_two,
            model_name="gpt-4o-mini",
            prompt_tokens=5,
            completion_tokens=5,
            total_tokens=10,
            cost_usd=Decimal("0.010000"),
        )

        older = django_timezone.now() - timedelta(days=1)
        LLMUsageRecord.objects.filter(pk=record_one.pk).update(created_at=older, updated_at=older)
        record_one.refresh_from_db()

        self.assertEqual(list(LLMUsageRecord.objects.for_media(media_one)), [record_one])
        self.assertEqual(
            list(LLMUsageRecord.objects.for_media(media_one.pk)),
            [record_one],
        )

        totals = list(LLMUsageRecord.objects.totals_by_day())
        self.assertEqual(len(totals), 2)
        self.assertEqual(totals[0]["day"], older.date())
        self.assertEqual(totals[0]["total_tokens"], 30)
        self.assertEqual(totals[0]["cost_usd"], Decimal("0.123456"))
        self.assertEqual(totals[1]["total_tokens"], 10)
        self.assertEqual(totals[1]["cost_usd"], Decimal("0.010000"))


class BackfillLLMUsageCommandTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="usage-cmd", password="pass")
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_command_creates_usage_records(self):
        media = Media.objects.create(
            media_location="uploads/ocr/cmd.png",
            ocr_data={"usage": DEFAULT_USAGE_PAYLOAD},
        )

        call_command("backfill_llm_usage")

        media.refresh_from_db()
        usage_record = media.llm_usage_record
        self.assertEqual(usage_record.prompt_tokens, DEFAULT_USAGE_PAYLOAD["prompt_tokens"])
        self.assertEqual(
            usage_record.cost_usd,
            Decimal(str(DEFAULT_USAGE_PAYLOAD["total_cost_usd"])),
        )

    def test_dry_run_reports_without_changes(self):
        Media.objects.create(
            media_location="uploads/ocr/cmd.png",
            ocr_data={"usage": DEFAULT_USAGE_PAYLOAD},
        )

        call_command("backfill_llm_usage", dry_run=True)

        self.assertFalse(LLMUsageRecord.objects.exists())


class ChatGPTUsageReportViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="staff-usage", password="pass", is_staff=True
        )
        self.standard_user = User.objects.create_user(
            username="standard-usage", password="pass", is_staff=False
        )
        self.url = reverse("admin-chatgpt-usage")

        older = django_timezone.now() - timedelta(days=7)
        newer = django_timezone.now() - timedelta(days=1)

        media_one = Media.objects.create(media_location="uploads/ocr/report-one.png")
        media_two = Media.objects.create(media_location="uploads/ocr/report-two.png")

        record_one = LLMUsageRecord.objects.create(
            media=media_one,
            model_name="gpt-4o",
            prompt_tokens=50,
            completion_tokens=25,
            total_tokens=75,
            cost_usd=Decimal("0.75"),
            processing_seconds=Decimal("1.50"),
        )
        record_two = LLMUsageRecord.objects.create(
            media=media_two,
            model_name="gpt-4o-mini",
            prompt_tokens=40,
            completion_tokens=40,
            total_tokens=80,
            cost_usd=Decimal("0.40"),
            processing_seconds=Decimal("2.25"),
            remaining_quota_usd=Decimal("7.50"),
        )

        LLMUsageRecord.objects.filter(pk=record_one.pk).update(
            created_at=older, updated_at=older
        )
        LLMUsageRecord.objects.filter(pk=record_two.pk).update(
            created_at=newer, updated_at=newer
        )

    def test_requires_staff_access(self):
        self.client.force_login(self.standard_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    @override_settings(LLM_USAGE_MONTHLY_BUDGET_USD=Decimal("10"))
    def test_renders_with_aggregated_totals(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        daily_totals = response.context["daily_totals"]
        weekly_totals = response.context["weekly_totals"]
        cumulative_cost = response.context["cumulative_cost"]
        budget_progress = response.context["budget_progress"]
        total_processing_seconds = response.context["total_processing_seconds"]
        avg_processing_seconds = response.context["avg_processing_seconds"]
        scans_processed = response.context["scans_processed"]
        remaining_quota = response.context["remaining_quota_usd"]

        self.assertEqual(len(daily_totals), 2)
        self.assertTrue(any(row["record_count"] == 1 for row in daily_totals))
        self.assertEqual(len(weekly_totals), 2)
        self.assertEqual(cumulative_cost, Decimal("1.15"))
        self.assertAlmostEqual(float(budget_progress), 11.5)
        self.assertEqual(total_processing_seconds, Decimal("3.75"))
        self.assertAlmostEqual(float(avg_processing_seconds), 1.875)
        self.assertEqual(scans_processed, 2)
        self.assertEqual(remaining_quota, Decimal("7.50"))

        self.assertContains(response, "Scans processed")
        self.assertContains(response, "Processing time")
        self.assertContains(response, "Remaining quota")

    def test_hides_remaining_quota_when_unavailable(self):
        LLMUsageRecord.objects.update(remaining_quota_usd=None)

        self.client.force_login(self.staff_user)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        self.assertIsNone(response.context["remaining_quota_usd"])
        self.assertNotContains(response, "Remaining quota")


class AdminAutocompleteTests(TestCase):
    """Ensure admin uses select2 autocomplete for heavy foreign keys."""

    def test_media_admin_autocomplete_fields(self):
        from django.contrib.admin.sites import site

        media_admin = site._registry[Media]
        self.assertEqual(
            list(media_admin.autocomplete_fields),
            ["accession", "accession_row", "scanning"],
        )

    def test_scanning_admin_search_fields(self):
        from django.contrib.admin.sites import site

        scanning_admin = site._registry[Scanning]
        self.assertIn("drawer__code", scanning_admin.search_fields)
        self.assertIn("user__username", scanning_admin.search_fields)
