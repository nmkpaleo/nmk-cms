from cms.models import Element
from cms.resources import ElementResource
from django.contrib.auth import get_user_model
from django.test import TestCase
from crum import set_current_user
from tablib import Dataset


class ElementImportCaseSensitivityTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="element-import")
        set_current_user(user)
        self.addCleanup(set_current_user, None)

    def test_id_updates_element_and_parent_name_is_matched_case_sensitively(self):
        lowercase_parent = Element.objects.create(name="mandible")
        element = Element.objects.create(name="femur")

        dataset = Dataset(headers=["id", "parent_element", "name"])
        dataset.append([element.pk, "Mandible", "Femur"])

        result = ElementResource().import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        imported = Element.objects.get(pk=element.pk)
        self.assertEqual(imported.name, "Femur")
        self.assertEqual(imported.parent_element.name, "Mandible")
        self.assertNotEqual(imported.parent_element, lowercase_parent)
        self.assertEqual(lowercase_parent.name, "mandible")

    def test_export_includes_element_id(self):
        element = Element.objects.create(name="Femur")

        dataset = ElementResource().export(queryset=Element.objects.filter(pk=element.pk))

        self.assertEqual(dataset.headers, ["id", "parent_element", "name"])
        self.assertEqual(str(dataset[0][0]), str(element.pk))

    def test_blank_id_imports_as_new_element(self):
        existing = Element.objects.create(name="Femur")
        dataset = Dataset(headers=["id", "parent_element", "name"])
        dataset.append(["", "", "Femur"])

        result = ElementResource().import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        self.assertEqual(Element.objects.filter(name="Femur").count(), 2)
        self.assertTrue(
            Element.objects.exclude(pk=existing.pk).filter(name="Femur").exists()
        )

    def test_missing_id_column_is_rejected(self):
        dataset = Dataset(headers=["parent_element", "name"])
        dataset.append(["", "Femur"])

        result = ElementResource().import_data(dataset, dry_run=False)

        self.assertTrue(result.has_errors())
        self.assertFalse(Element.objects.filter(name="Femur").exists())
