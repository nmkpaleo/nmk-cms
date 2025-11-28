from __future__ import annotations

from django.db import models
from django.test import SimpleTestCase
from django.test.utils import isolate_apps

from cms.merge.constants import MergeStrategy
from cms.merge.forms import FieldSelectionCandidate, FieldSelectionForm
from cms.merge.mixins import MergeMixin


@isolate_apps("cms")
class FieldSelectionFormTests(SimpleTestCase):
    def setUp(self):
        class Mergeable(MergeMixin):
            name = models.CharField(max_length=64)
            code = models.CharField(max_length=16, null=True, blank=True)

            class Meta:
                app_label = "cms"

        self.Model = Mergeable
        self.fields = [
            self.Model._meta.get_field("name"),
            self.Model._meta.get_field("code"),
        ]
        self.target = self.Model(pk=1, name="Target", code="TGT")
        self.source = self.Model(pk=2, name="Source", code=None)

    def test_builds_field_options_with_radio_choices(self):
        form = FieldSelectionForm(
            model=self.Model,
            merge_fields=self.fields,
            candidates=[
                FieldSelectionCandidate.from_instance(self.target, label="Target", role="target"),
                FieldSelectionCandidate.from_instance(self.source, label="Source", role="source"),
            ],
        )

        self.assertEqual(len(form.fields), 2)
        name_field = form.fields[form.selection_field_name("name")]
        self.assertEqual(name_field.initial, str(self.target.pk))

        name_options = form.field_options[0]["choices"]
        self.assertEqual(len(name_options), 2)
        self.assertTrue(name_options[0]["is_target"])
        self.assertEqual(name_options[1]["value"], "Source")

    def test_build_strategy_map_uses_roles_and_values(self):
        form = FieldSelectionForm(
            model=self.Model,
            merge_fields=self.fields,
            candidates=[
                FieldSelectionCandidate.from_instance(self.target, label="Target", role="target"),
                FieldSelectionCandidate.from_instance(self.source, label="Source", role="source"),
            ],
            data={
                FieldSelectionForm.selection_field_name("name"): str(self.source.pk),
                FieldSelectionForm.selection_field_name("code"): str(self.target.pk),
            },
        )

        self.assertTrue(form.is_valid())
        strategy = form.build_strategy_map()

        name_strategy = strategy["fields"]["name"]
        self.assertEqual(name_strategy["strategy"], MergeStrategy.FIELD_SELECTION.value)
        self.assertEqual(name_strategy["selected_from"], "source")

        code_strategy = strategy["fields"]["code"]
        self.assertEqual(code_strategy["selected_from"], "target")

    def test_custom_candidate_value_included_when_no_role(self):
        custom = self.Model(pk=3, name="Custom", code="CST")
        form = FieldSelectionForm(
            model=self.Model,
            merge_fields=self.fields,
            candidates=[custom],
            data={
                FieldSelectionForm.selection_field_name("name"): str(custom.pk),
                FieldSelectionForm.selection_field_name("code"): str(custom.pk),
            },
        )

        self.assertTrue(form.is_valid())
        strategy = form.build_strategy_map()

        self.assertEqual(strategy["fields"]["name"]["value"], "Custom")
        self.assertEqual(strategy["fields"]["code"]["value"], "CST")

    def test_invalid_selection_is_flagged(self):
        form = FieldSelectionForm(
            model=self.Model,
            merge_fields=self.fields,
            candidates=[self.target],
            data={
                FieldSelectionForm.selection_field_name("name"): "999",
                FieldSelectionForm.selection_field_name("code"): str(self.target.pk),
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn(FieldSelectionForm.selection_field_name("name"), form.errors)
