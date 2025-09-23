from unittest.mock import patch
from datetime import timedelta
from types import SimpleNamespace
import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
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
)
from cms.utils import generate_accessions_from_series
from cms.forms import DrawerRegisterForm, AccessionNumberSeriesAdminForm
from cms.filters import DrawerRegisterFilter
from cms.resources import DrawerRegisterResource, PlaceResource
from tablib import Dataset
from cms.upload_processing import process_file
from cms.ocr_processing import process_pending_scans


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
        upload = SimpleUploadedFile("2025-01-01(1).png", b"data", content_type="image/png")
        response = self.client.post(self.url, {"files": upload})
        self.assertEqual(response.status_code, 302)
        pending = Path(settings.MEDIA_ROOT) / "uploads" / "pending" / "2025-01-01(1).png"
        self.assertTrue(pending.exists())
        self.assertTrue(Media.objects.filter(media_location=f"uploads/pending/2025-01-01(1).png").exists())
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
        import shutil
        shutil.rmtree(rejected.parent.parent)


class OcrViewTests(TestCase):
    """Tests for the OCR processing view and link."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="cm", password="pass", is_staff=True)
        Group.objects.create(name="Collection Managers").user_set.add(self.user)
        self.url = reverse("admin-do-ocr")
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_login_required(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_admin_index_has_ocr_link(self):
        self.client.login(username="cm", password="pass")
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, self.url)

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch("cms.ocr_processing.chatgpt_ocr", return_value={"foo": "bar"})
    def test_ocr_moves_file_and_saves_json(self, mock_ocr, mock_detect):
        self.client.login(username="cm", password="pass")
        pending = Path(settings.MEDIA_ROOT) / "uploads" / "pending"
        pending.mkdir(parents=True, exist_ok=True)
        filename = "2025-01-01(1).png"
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
        import shutil
        shutil.rmtree(pending.parent)

    @patch("cms.views.process_pending_scans", return_value=(0, 1, 1, ["test.png: boom"]))
    def test_do_ocr_shows_error_details(self, mock_process):
        self.client.login(username="cm", password="pass")
        response = self.client.get(self.url, follow=True)
        self.assertContains(response, "0/1 scans OCR&#x27;d")
        self.assertContains(response, "OCR failed for 1 scans: test.png: boom")

    @patch("cms.views.process_pending_scans", return_value=(3, 0, 5, []))
    def test_do_ocr_reports_progress(self, mock_process):
        self.client.login(username="cm", password="pass")
        response = self.client.get(self.url, follow=True)
        self.assertContains(response, "3/5 scans OCR&#x27;d")


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
            successes, failures, total, errors = process_pending_scans()
        self.assertEqual(successes, 0)
        self.assertEqual(failures, 1)
        self.assertEqual(total, 1)
        self.assertTrue(any("boom" in e for e in errors))
        self.assertTrue(any("boom" in m for m in cm.output))
        media = Media.objects.get()
        self.assertEqual(media.ocr_status, Media.OCRStatus.FAILED)
        self.assertEqual(media.ocr_data["error"], "boom")
        self.assertEqual(media.media_location.name, f"uploads/failed/{filename}")
        failed_file = Path(settings.MEDIA_ROOT) / "uploads" / "failed" / filename
        self.assertTrue(failed_file.exists())

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch(
        "cms.ocr_processing.chatgpt_ocr",
        return_value={
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
        },
    )
    def test_creates_accession_and_links_media(self, mock_ocr, mock_detect):
        Collection.objects.create(abbreviation="KNM", description="Kenya")
        filename = "acc.png"
        file_path = self.pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")
        successes, failures, total, errors = process_pending_scans()
        self.assertEqual((successes, failures, total), (1, 0, 1))
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
        self.assertIn("_processed_accessions", media.ocr_data)
        repeat = media.transition_qc(Media.QCStatus.APPROVED, user=self.user)
        self.assertEqual(repeat["created"], [])
        self.assertEqual(Accession.objects.count(), 1)

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch(
        "cms.ocr_processing.chatgpt_ocr",
        return_value={
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
        },
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
            {
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
            },
            {
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
            },
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
        return_value={
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
        },
    )
    def test_existing_accession_reports_conflict(self, mock_ocr, mock_detect):
        collection = Collection.objects.create(abbreviation="KNM", description="Kenya")
        locality = Locality.objects.create(abbreviation="AB", name="Existing")
        Accession.objects.create(collection=collection, specimen_prefix=locality, specimen_no=123)
        filename = "acc2.png"
        file_path = self.pending / filename
        file_path.write_bytes(b"data")
        Media.objects.create(media_location=f"uploads/pending/{filename}")
        successes, failures, total, errors = process_pending_scans()
        self.assertEqual((successes, failures, total), (1, 0, 1))
        media = Media.objects.get()
        with self.assertRaises(ValidationError) as exc:
            media.transition_qc(Media.QCStatus.APPROVED, user=self.user)
        self.assertIn("Accession already exists", str(exc.exception))
        self.assertEqual(Accession.objects.count(), 1)
        media.refresh_from_db()
        self.assertEqual(media.qc_status, Media.QCStatus.PENDING_INTERN)
        self.assertEqual(media.qc_logs.filter(description__contains="Approval blocked").count(), 1)

    @patch("cms.ocr_processing.detect_card_type", return_value={"card_type": "accession_card"})
    @patch(
        "cms.ocr_processing.chatgpt_ocr",
        return_value={
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
        },
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
        return_value={
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
        },
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
        return_value={
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
        },
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
        return_value={
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
        },
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
        return_value={
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
        },
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
        return_value={
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
        },
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
        return_value={
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
        },
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


class UploadProcessingTests(TestCase):
    """Tests for the file watcher processing logic."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="intern", password="pass")
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.drawer = DrawerRegister.objects.create(
            code="DRW", description="Drawer", estimated_documents=1
        )
        start = now() - timedelta(minutes=5)
        end = now() + timedelta(minutes=5)
        self.scanning = Scanning.objects.create(
            drawer=self.drawer, user=self.user, start_time=start, end_time=end
        )

    def test_scanning_lookup_uses_creation_time(self):
        incoming = Path(settings.MEDIA_ROOT) / "uploads" / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        filename = "2025-09-09(1).png"
        src = incoming / filename
        src.write_bytes(b"data")
        created = self.scanning.start_time + timedelta(minutes=1)
        stat_result = SimpleNamespace(st_ctime=created.timestamp(), st_mode=0)
        with patch("pathlib.Path.stat", return_value=stat_result):
            process_file(src)
        media = Media.objects.get(media_location=f"uploads/pending/{filename}")
        self.assertEqual(media.scanning, self.scanning)
        import shutil
        shutil.rmtree(incoming.parent)


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
