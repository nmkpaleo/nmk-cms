from __future__ import annotations

import os

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

pytestmark = pytest.mark.usefixtures("django_db_setup")

from cms.merge.forms import FieldSelectionForm
from cms.merge.services import merge_accession_references
from cms.merge.views import FieldSelectionMergeView
from cms.models import (
    Accession,
    AccessionReference,
    Collection,
    Locality,
    Reference,
    MergeLog,
)


class AccessionReferenceMergeFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.collection = Collection.objects.create(
            abbreviation="COLL", description="Test collection"
        )
        cls.locality = Locality.objects.create(abbreviation="LOC", name="Locality")
        cls.accession = Accession.objects.create(
            collection=cls.collection,
            specimen_prefix=cls.locality,
            specimen_no=1,
        )
        cls.reference_a = Reference.objects.create(
            title="Reference A", first_author="Author", year="2023"
        )
        cls.reference_b = Reference.objects.create(
            title="Reference B", first_author="Author", year="2024"
        )
        cls.User = get_user_model()

    def setUp(self):
        self.staff = self.User.objects.create_superuser(
            username="staff", email="staff@example.com", password="pass"
        )
        self.client.login(username="staff", password="pass")

    def _create_references(self):
        target = AccessionReference.objects.create(
            accession=self.accession,
            reference=self.reference_a,
            page="10",
        )
        source = AccessionReference.objects.create(
            accession=self.accession,
            reference=self.reference_b,
            page="20",
        )
        return target, source

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_field_selection_merge_updates_reference_and_logs_history(self):
        target, source = self._create_references()
        history_model = target.history.model
        history_before = history_model.objects.filter(id=target.id).count()

        merge_fields = FieldSelectionMergeView().get_mergeable_fields(AccessionReference)
        data = {
            "model": AccessionReference._meta.label,
            "target": str(target.pk),
            "candidates": f"{target.pk},{source.pk}",
            "cancel": reverse("admin:cms_accessionreference_changelist"),
        }

        for field in merge_fields:
            field_name = FieldSelectionForm.selection_field_name(field.name)
            if field.name == "reference":
                data[field_name] = str(source.pk)
            elif field.name == "page":
                data[field_name] = str(source.pk)
            else:
                data[field_name] = str(target.pk)

        response = self.client.post(reverse("merge:merge_field_selection"), data)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(AccessionReference.objects.filter(pk=source.pk).exists())
        target.refresh_from_db()
        self.assertEqual(target.reference, self.reference_b)
        self.assertEqual(target.page, "20")

        history_after = history_model.objects.filter(id=target.id).count()
        self.assertGreater(history_after, history_before)

        log_exists = MergeLog.objects.filter(
            model_label=AccessionReference._meta.label,
            source_pk=str(source.pk),
            target_pk=str(target.pk),
        ).exists()
        self.assertTrue(log_exists)

    def test_field_selection_view_requires_staff(self):
        target, source = self._create_references()
        self.client.logout()
        user = self.User.objects.create_user(
            username="regular", email="regular@example.com", password="pass"
        )
        self.client.login(username=user.username, password="pass")

        response = self.client.get(
            reverse("merge:merge_field_selection"),
            {
                "model": AccessionReference._meta.label,
                "target": target.pk,
                "candidates": f"{target.pk},{source.pk}",
            },
        )

        self.assertEqual(response.status_code, 403)


class AccessionReferenceMergeServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        collection = Collection.objects.create(
            abbreviation="COLL2", description="Test collection"
        )
        locality = Locality.objects.create(abbreviation="LC2", name="Locality 2")
        cls.accession_one = Accession.objects.create(
            collection=collection,
            specimen_prefix=locality,
            specimen_no=1,
        )
        cls.accession_two = Accession.objects.create(
            collection=collection,
            specimen_prefix=locality,
            specimen_no=2,
        )
        cls.reference_one = Reference.objects.create(
            title="Reference One", first_author="A", year="2020"
        )
        cls.reference_two = Reference.objects.create(
            title="Reference Two", first_author="B", year="2021"
        )

    def test_merge_service_rejects_cross_accession_merge(self):
        source = AccessionReference.objects.create(
            accession=self.accession_one,
            reference=self.reference_one,
        )
        target = AccessionReference.objects.create(
            accession=self.accession_two,
            reference=self.reference_two,
        )

        with self.assertRaises(ValidationError) as excinfo:
            merge_accession_references(source=source, target=target)

        self.assertIn(
            _("Accession references must belong to the same accession."), excinfo.exception.messages
        )
