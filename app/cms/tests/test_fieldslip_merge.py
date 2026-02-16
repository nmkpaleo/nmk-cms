from __future__ import annotations

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import models
from django.test import RequestFactory, TransactionTestCase, override_settings
from django.urls import reverse
from unittest.mock import patch

from crum import impersonate

from cms.merge.constants import MergeStrategy
from cms.merge.engine import merge_records
from cms.models import (
    Accession,
    AccessionFieldSlip,
    Collection,
    FieldSlip,
    Locality,
)


class FieldSlipMergeDeduplicationTests(TransactionTestCase):

    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create(username="merge-admin")
        self.factory = RequestFactory()

        self._impersonation = impersonate(self.user)
        self._impersonation.__enter__()

        self.collection = Collection.objects.create(
            abbreviation="AA",
            description="Alpha Collection",
        )
        self.locality = Locality.objects.create(
            abbreviation="AL",
            name="Alpha Locality",
        )
        self.target = FieldSlip.objects.create(
            field_number="FS-001",
            verbatim_taxon="Taxon",
            verbatim_element="Element",
        )
        self.source = FieldSlip.objects.create(
            field_number="FS-002",
            verbatim_taxon="Taxon",
            verbatim_element="Element",
        )
        self.accession_one = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
        )
        self.accession_two = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=2,
        )

    def tearDown(self) -> None:
        self._impersonation.__exit__(None, None, None)
        super().tearDown()

    def _create_accession_links(self) -> tuple[AccessionFieldSlip, AccessionFieldSlip, AccessionFieldSlip]:
        target_link = AccessionFieldSlip.objects.create(
            accession=self.accession_one,
            fieldslip=self.target,
        )
        duplicate_link = AccessionFieldSlip.objects.create(
            accession=self.accession_one,
            fieldslip=self.source,
        )
        unique_link = AccessionFieldSlip.objects.create(
            accession=self.accession_two,
            fieldslip=self.source,
        )
        return target_link, duplicate_link, unique_link

    def test_merge_skips_duplicate_accession_links(self) -> None:
        self._create_accession_links()

        result = merge_records(
            self.source,
            self.target,
            strategy_map=None,
            archive=False,
        )

        target_links = list(
            AccessionFieldSlip.objects.filter(fieldslip=self.target)
            .order_by("accession_id")
            .values_list("accession_id", flat=True)
        )
        self.assertEqual(
            target_links,
            [self.accession_one.id, self.accession_two.id],
        )
        self.assertFalse(
            AccessionFieldSlip.objects.filter(fieldslip=self.source).exists()
        )
        self.assertEqual(
            AccessionFieldSlip.objects.count(),
            2,
        )

        relation_log = result.relation_actions.get("accession_links", {})
        self.assertEqual(relation_log.get("updated"), 1)
        self.assertEqual(relation_log.get("deleted"), 1)
        self.assertEqual(relation_log.get("skipped"), 1)

    def test_merge_dry_run_preserves_accession_links(self) -> None:
        self._create_accession_links()

        result = merge_records(
            self.source,
            self.target,
            strategy_map=None,
            dry_run=True,
            archive=False,
        )

        target_links = list(
            AccessionFieldSlip.objects.filter(fieldslip=self.target)
            .order_by("accession_id")
            .values_list("accession_id", flat=True)
        )
        self.assertEqual(target_links, [self.accession_one.id])
        source_links = list(
            AccessionFieldSlip.objects.filter(fieldslip=self.source)
            .order_by("accession_id")
            .values_list("accession_id", flat=True)
        )
        self.assertEqual(
            source_links,
            [self.accession_one.id, self.accession_two.id],
        )
        relation_log = result.relation_actions.get("accession_links", {})
        self.assertEqual(relation_log.get("updated"), 1)
        self.assertEqual(relation_log.get("skipped"), 1)
        self.assertEqual(relation_log.get("would_delete"), 1)

    def test_merge_records_emit_history_for_removed_duplicates(self) -> None:
        _, duplicate_link, _ = self._create_accession_links()

        merge_records(
            self.source,
            self.target,
            strategy_map=None,
            archive=False,
        )

        history_entries = list(
            AccessionFieldSlip.history.filter(id=duplicate_link.id)
            .order_by("-history_date")
            .values_list("history_type", flat=True)
        )
        self.assertGreaterEqual(len(history_entries), 2)
        self.assertIn("-", history_entries)

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_admin_merge_reports_duplicate_resolution(self) -> None:
        staff_user = get_user_model().objects.create_user(
            username="fieldslip-admin",
            password="test-pass",
            is_staff=True,
        )
        permission = Permission.objects.get(
            codename="can_merge",
            content_type=ContentType.objects.get_for_model(FieldSlip),
        )
        staff_user.user_permissions.add(permission)

        admin_instance = admin.site._registry[FieldSlip]

        AccessionFieldSlip.objects.create(
            accession=self.accession_one,
            fieldslip=self.target,
        )
        AccessionFieldSlip.objects.create(
            accession=self.accession_one,
            fieldslip=self.source,
        )
        AccessionFieldSlip.objects.create(
            accession=self.accession_two,
            fieldslip=self.source,
        )

        merge_fields = admin_instance.get_mergeable_fields()
        form_data: dict[str, str] = {
            "selected_ids": f"{self.target.pk},{self.source.pk}",
            "source": str(self.source.pk),
            "target": str(self.target.pk),
        }
        for field in merge_fields:
            strategy_name = admin_instance.merge_form_class.strategy_field_name(field.name)
            manual_name = admin_instance.merge_form_class.value_field_name(field.name)
            form_data[strategy_name] = MergeStrategy.PREFER_NON_NULL.value
            value = getattr(self.target, field.name, "")
            if isinstance(value, models.Model):
                form_data[manual_name] = str(value.pk)
            elif value in (None, ""):
                form_data[manual_name] = ""
            else:
                form_data[manual_name] = str(value)

        request = self.factory.post("/admin/cms/fieldslip/merge/", data=form_data)
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        request.user = staff_user
        setattr(request, "_messages", FallbackStorage(request))

        with patch("cms.admin_merge.reverse") as mock_reverse, patch(
            "cms.merge.engine._log_merge"
        ) as mock_log_merge:
            def fake_reverse(name: str, *args, **kwargs) -> str:
                if name == "merge:merge_candidate_search":
                    return "/admin/cms/fieldslip/merge/search/"
                return reverse(name, *args, **kwargs)

            mock_reverse.side_effect = fake_reverse
            mock_log_merge.return_value = None
            response = admin_instance.merge_view(request)
        self.assertEqual(response.status_code, 302)

        target_links = list(
            AccessionFieldSlip.objects.filter(fieldslip=self.target)
            .order_by("accession_id")
            .values_list("accession_id", flat=True)
        )
        self.assertEqual(
            target_links,
            [self.accession_one.id, self.accession_two.id],
        )

        messages = [message.message for message in get_messages(request)]
        self.assertTrue(any("Relation updates" in message for message in messages))
        self.assertTrue(any("deleted" in message for message in messages))
