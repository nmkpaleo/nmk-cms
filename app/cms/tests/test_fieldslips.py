from __future__ import annotations

import os
import sys
from pathlib import Path

from crum import set_current_user
from django.apps import apps
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

if not apps.ready:
    import django

    django.setup()

from cms.filters import FieldSlipFilter
from cms.models import (
    Accession,
    AccessionFieldSlip,
    AccessionRow,
    Collection,
    Element,
    FieldSlip,
    SedimentaryFeature,
    Identification,
    Locality,
    NatureOfSpecimen,
    Storage,
)


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

    def create_collection(self, abbreviation: str = "C1", description: str | None = None) -> Collection:
        return Collection.objects.create(
            abbreviation=abbreviation,
            description=description or f"Collection {abbreviation}",
        )

    def create_locality(self, abbreviation: str = "L1", name: str | None = None) -> Locality:
        return Locality.objects.create(
            abbreviation=abbreviation,
            name=name or f"Locality {abbreviation}",
            geological_times=[],
        )

    def create_storage(self, area: str = "Main Area") -> Storage:
        return Storage.objects.create(area=area)

    def create_accession(
        self,
        *,
        fieldslip: FieldSlip,
        specimen_no: int,
        is_published: bool = False,
        taxon: str | None = None,
        element_name: str | None = None,
    ) -> Accession:
        collection = self.create_collection(abbreviation=f"C{specimen_no}")
        locality = self.create_locality(abbreviation=f"L{specimen_no}")
        accession = Accession.objects.create(
            collection=collection,
            specimen_prefix=locality,
            specimen_no=specimen_no,
            accessioned_by=self.user,
            is_published=is_published,
        )

        row = AccessionRow.objects.create(
            accession=accession,
            storage=self.create_storage(area=f"Area {specimen_no}"),
        )

        if taxon:
            Identification.objects.create(accession_row=row, taxon_verbatim=taxon, taxon=taxon)

        if element_name:
            element = Element.objects.create(name=element_name)
            NatureOfSpecimen.objects.create(accession_row=row, element=element)

        AccessionFieldSlip.objects.create(accession=accession, fieldslip=fieldslip)

        return accession


class FieldSlipFilterTests(FieldSlipTestCase):
    def test_filter_matches_partial_field_number(self):
        matching = self.create_fieldslip(field_number="FS-100")
        self.create_fieldslip(field_number="FS-200")

        filterset = FieldSlipFilter(data={"field_number": "100"}, queryset=FieldSlip.objects.all())

        results = list(filterset.qs)
        self.assertEqual(results, [matching])

    def test_filter_by_sedimentary_feature_and_surface_exposure(self):
        feature = SedimentaryFeature.objects.create(
            name="ROOT/BUR FEATURE",
            code="ROOT_BUR_FEATURE",
            category="sedimentary",
        )
        matching = self.create_fieldslip(field_number="FS-201")
        matching.surface_exposure = True
        matching.save(update_fields=["surface_exposure"])
        matching.sedimentary_features.add(feature)

        non_matching = self.create_fieldslip(field_number="FS-202")
        non_matching.surface_exposure = False
        non_matching.save(update_fields=["surface_exposure"])

        filterset = FieldSlipFilter(
            data={
                "sedimentary_features": [str(feature.pk)],
                "surface_exposure": "true",
            },
            queryset=FieldSlip.objects.all(),
        )

        self.assertTrue(filterset.form.is_valid())
        self.assertEqual(list(filterset.qs), [matching])


class FieldSlipListPermissionTests(FieldSlipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.curator_group, _ = Group.objects.get_or_create(name="Curators")
        self.curator = get_user_model().objects.create_user(
            username="curator-user",
            email="curator@example.com",
            password="pass1234",
        )
        self.curator.groups.add(self.curator_group)

        self.regular_user = get_user_model().objects.create_user(
            username="regular-user",
            email="regular@example.com",
            password="pass1234",
        )

    def test_curator_can_access_fieldslip_list(self):
        self.client.force_login(self.curator)

        response = self.client.get(reverse("fieldslip_list"))

        self.assertEqual(response.status_code, 200)

    def test_non_manager_non_curator_is_forbidden(self):
        self.client.force_login(self.regular_user)

        response = self.client.get(reverse("fieldslip_list"))

        self.assertEqual(response.status_code, 403)


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


class FieldSlipAccessionsRenderingTests(FieldSlipTestCase):
    def test_manager_sees_published_and_unpublished_accessions(self):
        slip = self.create_fieldslip(field_number="FS-300")
        published = self.create_accession(
            fieldslip=slip,
            specimen_no=301,
            is_published=True,
            taxon="Equus caballus",
            element_name="Molar",
        )
        unpublished = self.create_accession(
            fieldslip=slip,
            specimen_no=302,
            is_published=False,
            taxon="Canis lupus",
            element_name="Ulna",
        )

        self.client.force_login(self.user)

        response = self.client.get(reverse("fieldslip_detail", args=[slip.pk]))

        content = response.content.decode()
        self.assertContains(response, str(published.specimen_no))
        self.assertContains(response, str(unpublished.specimen_no))
        self.assertIn("Equus caballus", content)
        self.assertIn("Canis lupus", content)
        self.assertIn("Accessioned by", content)

    def test_anonymous_user_only_sees_published_accessions(self):
        slip = self.create_fieldslip(field_number="FS-310")
        published = self.create_accession(
            fieldslip=slip,
            specimen_no=311,
            is_published=True,
        )
        unpublished = self.create_accession(
            fieldslip=slip,
            specimen_no=312,
            is_published=False,
        )

        self.client.logout()

        response = self.client.get(reverse("fieldslip_detail", args=[slip.pk]))

        content = response.content.decode()
        self.assertContains(response, str(published.specimen_no))
        self.assertNotIn(str(unpublished.specimen_no), content)
        self.assertNotIn("Accessioned by", content)

    def test_accession_section_shows_empty_state_when_no_links(self):
        slip = self.create_fieldslip(field_number="FS-320")

        response = self.client.get(reverse("fieldslip_detail", args=[slip.pk]))

        self.assertContains(
            response,
            "No related accessions recorded for this field slip.",
        )
