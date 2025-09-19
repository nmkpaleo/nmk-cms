from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from crum import set_current_user

from cms.forms import AccessionRowIdentificationForm
from cms.models import Reference


class ReferenceAutocompleteTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester",
            password="secret",
            is_staff=True,
        )

    def _get_field_id(self, form):
        """Render the widget so django-select2 stores it in the cache."""
        form["reference"].as_widget()
        return form.fields["reference"].widget.field_id

    def test_autocomplete_returns_matches_after_three_characters(self):
        set_current_user(self.user)
        Reference.objects.create(
            title="A study on beetles",
            first_author="Smith",
            year="1999",
            citation="Smith, 1999",
        )
        Reference.objects.create(
            title="Catalog of butterflies",
            first_author="Doe",
            year="2001",
            citation="Doe, 2001",
        )
        set_current_user(None)

        form = AccessionRowIdentificationForm()
        field_id = self._get_field_id(form)

        client = Client()
        client.force_login(self.user)

        url = reverse("reference-autocomplete")
        response = client.get(url, {"term": "cat", "field_id": field_id})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("results", payload)
        texts = [entry["text"] for entry in payload["results"]]
        self.assertIn("Doe, 2001", texts)

    def test_autocomplete_requires_three_characters(self):
        set_current_user(self.user)
        Reference.objects.create(
            title="Bird atlas",
            first_author="Jones",
            year="1995",
            citation="Jones, 1995",
        )
        set_current_user(None)

        form = AccessionRowIdentificationForm()
        field_id = self._get_field_id(form)

        client = Client()
        client.force_login(self.user)

        url = reverse("reference-autocomplete")
        response = client.get(url, {"term": "bi", "field_id": field_id})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"], [])
