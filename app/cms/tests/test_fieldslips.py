from __future__ import annotations

import os
import sys
from pathlib import Path

from crum import set_current_user
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

# Ensure Django can locate the project settings when the module is executed directly
BASE_DIR = Path(__file__).resolve().parents[3]
APP_DIR = BASE_DIR / "app"
for path in (BASE_DIR, APP_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.config.settings")
os.environ.setdefault("DB_ENGINE", "django.db.backends.sqlite3")

from cms.filters import FieldSlipFilter
from cms.models import FieldSlip


class FieldSlipTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_group, _ = Group.objects.get_or_create(name="Collection Managers")

    def setUp(self) -> None:
        super().setUp()
        self.user = get_user_model().objects.create_user(
            username="manager",
            email="manager@example.com",
            password="pass1234",
        )
        self.user.groups.add(self.manager_group)
        set_current_user(self.user)

    def tearDown(self) -> None:
        set_current_user(None)
        super().tearDown()

    def create_fieldslip(
        self,
        *,
        field_number: str,
        collector: str | None = "Collector",
        aerial_photo: str | None = None,
    ) -> FieldSlip:
        return FieldSlip.objects.create(
            field_number=field_number,
            collector=collector,
            verbatim_taxon="Taxonus example",
            verbatim_element="Elementus",
            aerial_photo=aerial_photo,
        )


class FieldSlipFilterTests(FieldSlipTestCase):
    def test_filter_matches_partial_field_number(self):
        matching = self.create_fieldslip(field_number="FS-100")
        self.create_fieldslip(field_number="FS-200")

        filterset = FieldSlipFilter(data={"field_number": "100"}, queryset=FieldSlip.objects.all())

        results = list(filterset.qs)
        self.assertEqual(results, [matching])


class FieldSlipAerialPhotoRenderingTests(FieldSlipTestCase):
    def test_detail_renders_aerial_photo_as_text(self):
        slip = self.create_fieldslip(field_number="FS-101", aerial_photo="AP-007")

        response = self.client.get(reverse("fieldslip_detail", args=[slip.pk]))

        content = response.content.decode()
        self.assertIn("fa-solid fa-map-location-dot", content)
        self.assertIn("AP-007", content)
        self.assertIn("w3-tag w3-light-blue", content)

    def test_detail_shows_fallback_message_when_missing_aerial_photo(self):
        slip = self.create_fieldslip(field_number="FS-102", aerial_photo=None)

        response = self.client.get(reverse("fieldslip_detail", args=[slip.pk]))

        content = response.content.decode()
        self.assertIn("No aerial photo information provided.", content)

    def test_list_filters_by_field_number_and_renders_textual_aerial_photo(self):
        matching = self.create_fieldslip(field_number="FS-103", aerial_photo="AP-103")
        self.create_fieldslip(field_number="FS-200", aerial_photo="AP-200")

        self.client.force_login(self.user)

        response = self.client.get(reverse("fieldslip_list"), {"field_number": matching.field_number})

        content = response.content.decode()
        self.assertIn(matching.field_number, content)
        self.assertIn("AP-103", content)
        self.assertIn("fa-solid fa-map-location-dot", content)
        self.assertIn("w3-tag w3-round w3-light-blue", content)
        self.assertNotIn("FS-200", content)
        self.assertNotIn("AP-200", content)
