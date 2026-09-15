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

    def test_selection_page_does_not_render_external_cancel_url(self):
        with impersonate(self.user):
            Element.objects.create(name="Femur")

        response = self.client.get(
            reverse("merge:merge_element_selection"),
            {"cancel": "https://evil.example/phish"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "evil.example")
        self.assertNotContains(response, 'name="cancel"')

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
        self.assertEqual(response["Location"], reverse("merge:merge_element_review"))

        review_payload = self.client.session["merge_element_review"]
        self.assertEqual(review_payload["target"], str(target.pk))
        self.assertEqual(review_payload["candidates"], f"{target.pk},{source.pk}")

    def test_selection_post_does_not_propagate_external_cancel_url(self):
        with impersonate(self.user):
            target = Element.objects.create(name="Target")
            source = Element.objects.create(name="Source")

        response = self.client.post(
            reverse("merge:merge_element_selection"),
            {
                "target": str(target.pk),
                "source_ids": [str(source.pk)],
                "cancel": "https://evil.example/phish",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("merge:merge_element_review"))
        self.assertEqual(
            self.client.session["merge_element_review"]["cancel"],
            reverse("merge:merge_element_selection"),
        )

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

    def test_review_page_uses_session_selection_after_post(self):
        with impersonate(self.user):
            target = Element.objects.create(name="Target")
            source = Element.objects.create(name="Source")

        self.client.post(
            reverse("merge:merge_element_selection"),
            {
                "target": str(target.pk),
                "source_ids": [str(source.pk)],
                "cancel": "/admin/cms/element/",
            },
        )

        response = self.client.get(reverse("merge:merge_element_review"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, target.name)
        self.assertContains(response, source.name)
        self.assertContains(
            response,
            '<input type="hidden" name="cancel" value="/admin/cms/element/" />',
            html=False,
        )
