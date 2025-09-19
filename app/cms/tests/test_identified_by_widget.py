from django.contrib.auth import get_user_model
from django.test import TestCase

from crum import set_current_user

from cms.forms import AccessionRowIdentificationForm
from cms.models import Person


User = get_user_model()


class IdentifiedByWidgetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="secret")
        set_current_user(self.user)

    def tearDown(self):
        set_current_user(None)

    def identification_form(self, identified_by):
        return AccessionRowIdentificationForm(
            data={
                "identified_by": identified_by,
                "taxon": "",
                "reference": "",
                "date_identified": "",
                "identification_qualifier": "",
                "verbatim_identification": "",
                "identification_remarks": "",
            }
        )

    def test_existing_person_choice_is_valid(self):
        person = Person.objects.create(first_name="Rene", last_name="Bobe")

        form = self.identification_form(str(person.pk))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["identified_by"], person)

    def test_creates_person_from_space_separated_name(self):
        form = self.identification_form("Jane Mary Doe")

        self.assertTrue(form.is_valid(), form.errors)
        person = Person.objects.get(first_name="Jane", last_name="Mary Doe")
        self.assertEqual(form.cleaned_data["identified_by"], person)

    def test_creates_person_from_comma_separated_name(self):
        form = self.identification_form("Doe, John")

        self.assertTrue(form.is_valid(), form.errors)
        person = Person.objects.get(first_name="John", last_name="Doe")
        self.assertEqual(form.cleaned_data["identified_by"], person)

    def test_rejects_single_word_names(self):
        form = self.identification_form("Cher")

        self.assertFalse(form.is_valid())
        self.assertIn("identified_by", form.errors)
        self.assertIn("Enter both first and last names", form.errors["identified_by"][0])
