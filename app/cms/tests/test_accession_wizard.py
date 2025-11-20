from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from crum import set_current_user

from cms.models import AccessionNumberSeries, Collection, Locality


class AccessionWizardSpecimenNumberTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="wizard-user",
            password="pass1234",
            email="wizard@example.com",
        )
        set_current_user(self.user)
        self.collection = Collection.objects.create(
            abbreviation="AB",
            description="Accession Collection",
        )
        self.locality = Locality.objects.create(
            abbreviation="LC",
            name="Locality City",
        )
        AccessionNumberSeries.objects.create(
            user=self.user,
            start_from=100,
            end_at=110,
            current_number=100,
            is_active=True,
        )

    def tearDown(self):
        set_current_user(None)

    def test_specimen_number_is_rendered_readonly_on_accession_step(self):
        self.client.login(username="wizard-user", password="pass1234")

        start_response = self.client.get(reverse("accession-wizard"))
        self.assertEqual(start_response.status_code, 200)
        management_form = start_response.context["wizard"]["management_form"]
        current_step_field = management_form.add_prefix("current_step")

        response = self.client.post(
            reverse("accession-wizard"),
            data={
                current_step_field: "0",
                "0-accession_number": "100",
            },
        )

        self.assertEqual(response.status_code, 200)
        wizard = response.context.get("wizard")
        self.assertIsNotNone(wizard)
        accession_form = wizard["form"]
        self.assertTrue(accession_form.fields["specimen_no"].disabled)

        self.assertContains(response, "Specimen no")
        self.assertContains(
            response,
            '<input type="hidden" name="1-specimen_no" value="100"',
            html=False,
        )
        self.assertContains(response, "100")
