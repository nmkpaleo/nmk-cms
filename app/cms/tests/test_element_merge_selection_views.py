from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from crum import impersonate

from cms.models import Element


@override_settings(MERGE_TOOL_FEATURE=True, ALLOWED_HOSTS=["testserver", "localhost"])
class ElementMergeSelectionViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="element-selector",
            password="pw",
            is_staff=True,
        )
        permission = Permission.objects.get(
            codename="can_merge",
            content_type__app_label="cms",
            content_type__model="element",
        )
        self.user.user_permissions.add(permission)
        self.client.force_login(self.user)

    def test_selection_page_renders(self):
        with impersonate(self.user):
            Element.objects.create(name="Femur")
        url = reverse("merge:merge_element_selection")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Merge elements")

    def test_selection_post_redirects_to_review(self):
        with impersonate(self.user):
            target = Element.objects.create(name="Target")
            source = Element.objects.create(name="Source")

        url = reverse("merge:merge_element_selection")
        response = self.client.post(
            url,
            {
                "target": str(target.pk),
                "source_ids": [str(source.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("merge:merge_element_review"), response["Location"])
        self.assertIn(str(target.pk), response["Location"])
        self.assertIn(str(source.pk), response["Location"])

    def test_review_page_renders_field_selection(self):
        with impersonate(self.user):
            target = Element.objects.create(name="Target")
            source = Element.objects.create(name="Source")

        review_url = reverse("merge:merge_element_review")
        params = {
            "target": str(target.pk),
            "candidates": f"{target.pk},{source.pk}",
        }
        response = self.client.get(review_url, params)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Review selections")
        self.assertContains(response, target.name)
        self.assertContains(response, source.name)
