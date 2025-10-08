from django.apps import apps
from django.test import TestCase, override_settings

from cms.merge import MERGE_REGISTRY
from cms.models import FieldSlip, Reference, Storage


@override_settings(MERGE_TOOL_FEATURE=True)
class MergeRegistryRegistrationTests(TestCase):
    def setUp(self):
        self.app_config = apps.get_app_config("cms")
        self._previous_entries = {}
        for model in (FieldSlip, Storage, Reference):
            if model in MERGE_REGISTRY:
                self._previous_entries[model] = MERGE_REGISTRY[model]
                MERGE_REGISTRY.pop(model)

    def tearDown(self):
        for model in (FieldSlip, Storage, Reference):
            MERGE_REGISTRY.pop(model, None)
            if model in self._previous_entries:
                MERGE_REGISTRY[model] = self._previous_entries[model]

    def test_ready_registers_default_merge_models(self):
        self.app_config._register_merge_models()
        for model in (FieldSlip, Storage, Reference):
            self.assertIn(model, MERGE_REGISTRY)
