from cms.models import Element
from cms.resources import ElementResource
from django.contrib.auth import get_user_model
from django.test import TestCase
from crum import set_current_user
from tablib import Dataset


class ElementImportCaseSensitivityTests(TestCase):
    def test_name_and_parent_element_imports_are_case_sensitive(self):
        self.assertEqual(ElementResource().get_import_id_fields(), ["name"])
        user = get_user_model().objects.create_user(username="element-import")
        set_current_user(user)
        self.addCleanup(set_current_user, None)

        lowercase_parent = Element.objects.create(name="mandible")
        lowercase_element = Element.objects.create(name="femur", parent_element=lowercase_parent)

        dataset = Dataset(headers=["parent_element", "name"])
        dataset.append(["Mandible", "Femur"])

        result = ElementResource().import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        self.assertEqual(Element.objects.filter(name="Femur").count(), 1)
        imported = Element.objects.get(name="Femur")
        self.assertEqual(imported.parent_element.name, "Mandible")
        self.assertEqual(Element.objects.get(pk=lowercase_element.pk).parent_element, lowercase_parent)