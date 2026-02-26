from __future__ import annotations
from crum import impersonate
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from cms.merge.forms import ElementFieldSelectionForm, FieldSelectionCandidate
from cms.models import Element




class ElementFieldSelectionFormTests(TestCase):
    def test_builds_selected_fields(self):
        user = get_user_model().objects.create(username="creator")
        with impersonate(user):
            parent = Element.objects.create(name="Parent")
            target = Element.objects.create(name="Target", parent_element=parent)
            source = Element.objects.create(name="Source", parent_element=None)

        data = {
            ElementFieldSelectionForm.selection_field_name("name"): str(source.pk),
            ElementFieldSelectionForm.selection_field_name("parent_element"): str(target.pk),
        }

        form = ElementFieldSelectionForm(
            candidates=[
                FieldSelectionCandidate.from_instance(target, role="target"),
                FieldSelectionCandidate.from_instance(source, role="source"),
            ],
            data=data,
        )

        self.assertTrue(form.is_valid())

        selected = form.build_selected_fields()
        self.assertEqual(selected, {"name": "Source", "parent_element": "target"})


@override_settings(MERGE_TOOL_FEATURE=True, ALLOWED_HOSTS=["testserver", "localhost"])
class ElementFieldSelectionViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="merger", password="pw", is_staff=True
        )
        permission = Permission.objects.get(
            codename="can_merge",
            content_type__app_label="cms",
            content_type__model="element",
        )
        self.user.user_permissions.add(permission)
        self.client.force_login(self.user)

    def test_merges_sources(self):
        with impersonate(self.user):
            parent = Element.objects.create(name="Parent")
            target = Element.objects.create(name="Target", parent_element=parent)
            source = Element.objects.create(name="Source", parent_element=None)

        url = reverse("merge:merge_element_field_selection")
        data = {
            "model": Element._meta.label,
            "target": str(target.pk),
            "candidates": f"{target.pk},{source.pk}",
            ElementFieldSelectionForm.selection_field_name("name"): str(source.pk),
            ElementFieldSelectionForm.selection_field_name("parent_element"): str(target.pk),
        }

        response = self.client.post(url, data=data)

        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertEqual(target.name, "Source")
        self.assertEqual(target.parent_element, parent)
        self.assertFalse(Element.objects.filter(pk=source.pk).exists())

    def test_requires_permission(self):
        another_user = get_user_model().objects.create_user(
            username="nope", password="pw", is_staff=True
        )
        client = Client()
        client.force_login(another_user)

        with impersonate(another_user):
            target = Element.objects.create(name="Target")
            source = Element.objects.create(name="Source")

        url = reverse("merge:merge_element_field_selection")
        params = {
            "model": Element._meta.label,
            "target": str(target.pk),
            "candidates": f"{target.pk},{source.pk}",
        }

        response = client.get(url, params)

        self.assertEqual(response.status_code, 403)
