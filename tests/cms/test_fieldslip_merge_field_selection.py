from __future__ import annotations

import pytest
from crum import set_current_user
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import patch

from cms.merge.forms import FieldSelectionForm
from cms.merge.views import FieldSelectionMergeView
from cms.models import FieldSlip, GrainSize


pytestmark = pytest.mark.django_db


class FieldSlipMergeFieldSelectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.User = get_user_model()
        cls._creator = cls.User.objects.create_user(username="fieldslip-merge-seeder")
        set_current_user(cls._creator)
        cls.grain_size_a = GrainSize.objects.create(name="Fine")
        cls.grain_size_b = GrainSize.objects.create(name="Coarse")
        set_current_user(None)

    def setUp(self):
        self.staff = self.User.objects.create_superuser(
            username="merge_staff", email="merge@example.com", password="pass"
        )
        self.client.login(username="merge_staff", password="pass")
        self.user_patcher = patch("cms.models.get_current_user", return_value=self.staff)
        self.user_patcher.start()
        self.addCleanup(self.user_patcher.stop)

    def _create_fieldslips(self):
        target = FieldSlip.objects.create(
            field_number="FS-TARGET",
            collector="Collector",
            verbatim_taxon="Pan",
            verbatim_element="M1",
            matrix_grain_size=self.grain_size_a,
        )
        source = FieldSlip.objects.create(
            field_number="FS-SOURCE",
            collector="Collector",
            verbatim_taxon="Pan",
            verbatim_element="M2",
            matrix_grain_size=self.grain_size_b,
        )
        return target, source

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_field_selection_merge_accepts_foreign_key_selection(self):
        target, source = self._create_fieldslips()

        merge_fields = FieldSelectionMergeView().get_mergeable_fields(FieldSlip)
        data = {
            "model": FieldSlip._meta.label,
            "target": str(target.pk),
            "candidates": f"{target.pk},{source.pk}",
            "cancel": reverse("admin:cms_fieldslip_changelist"),
        }

        for field in merge_fields:
            select_name = FieldSelectionForm.selection_field_name(field.name)
            if field.name in {"matrix_grain_size", "verbatim_element"}:
                data[select_name] = str(source.pk)
            else:
                data[select_name] = str(target.pk)

        response = self.client.post(reverse("merge:merge_field_selection"), data)

        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertEqual(target.matrix_grain_size, self.grain_size_b)
        self.assertEqual(target.verbatim_element, "M2")
