from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from crum import set_current_user

from cms.models import (
    Accession,
    AccessionNumberSeries,
    Collection,
    Element,
    Locality,
    Person,
    Storage,
)


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
        self.storage = Storage.objects.create(area="A1")
        self.element = Element.objects.create(name="Femur")
        self.person = Person.objects.create(first_name="Ada", last_name="Lovelace")
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

    def test_specimen_number_saved_from_step_zero_selection(self):
        self.client.login(username="wizard-user", password="pass1234")

        start_response = self.client.get(reverse("accession-wizard"))
        management_form = start_response.context["wizard"]["management_form"]
        current_step_field = management_form.add_prefix("current_step")

        accession_step_response = self.client.post(
            reverse("accession-wizard"),
            data={
                current_step_field: "0",
                "0-accession_number": "100",
            },
        )
        self.assertEqual(accession_step_response.status_code, 200)

        accession_management = accession_step_response.context["wizard"]["management_form"]
        accession_current_step = accession_management.add_prefix("current_step")

        specimen_step_response = self.client.post(
            reverse("accession-wizard"),
            data={
                accession_current_step: "1",
                "1-collection": self.collection.pk,
                "1-specimen_prefix": self.locality.pk,
                "1-specimen_no": "105",  # Attempt to change specimen number
                "1-type_status": "",
                "1-comment": "",
            },
        )
        self.assertEqual(specimen_step_response.status_code, 200)

        specimen_management = specimen_step_response.context["wizard"]["management_form"]
        specimen_current_step = specimen_management.add_prefix("current_step")

        final_response = self.client.post(
            reverse("accession-wizard"),
            data={
                specimen_current_step: "2",
                "2-storage": self.storage.pk,
                "2-element": self.element.pk,
                "2-side": "left",
                "2-condition": "complete",
                "2-fragments": 0,
                "2-taxon": "Test taxon",
                "2-identified_by": self.person.pk,
            },
        )

        accession = Accession.objects.latest("id")
        self.assertRedirects(
            final_response,
            reverse("accession_detail", args=[accession.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(accession.specimen_no, 100)
