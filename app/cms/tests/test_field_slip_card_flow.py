from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from cms.models import (
    Accession,
    AccessionFieldSlip,
    Collection,
    FieldSlip,
    Locality,
    Media,
    SedimentaryFeature,
)
from cms.ocr_processing import create_accessions_from_media, normalize_field_slip_payload
from cms.views import MediaQCFormManager


class FieldSlipCardNormalizationTests(TestCase):
    def test_normalize_payload_uses_source_label_for_marked_checkboxes(self):
        payload = {
            "card_type": "field_slip",
            "field_slip": {
                "checkboxes": {
                    "sedimentary_features": [
                        {"source_label": "MUD CRACKS", "mark": "✓"},
                        {"source_label": "X-BEDS", "checked": True},
                        {"source_label": "ROOT/BUR", "checked": False},
                    ],
                    "recommended_methods": [
                        {"source_label": "SIEVING", "marker": "x"},
                    ],
                }
            },
        }

        normalized = normalize_field_slip_payload(payload)

        self.assertEqual(
            normalized["checkboxes"]["sedimentary_features"],
            ["MUD CRACKS", "X-BEDS"],
        )
        self.assertEqual(normalized["checkboxes"]["recommended_methods"], ["SIEVING"])


class FieldSlipCardCreationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="tester", password="pass")
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_create_accessions_from_field_slip_card_creates_accession_and_link(self):
        Collection.objects.create(abbreviation="KNM", description="Kenya")
        feature = SedimentaryFeature.objects.filter(name__iexact="MUD CRACKS").first()
        if feature is None:
            feature = SedimentaryFeature.objects.filter(code="MUD_CRACKS").first()
        if feature is None:
            feature = SedimentaryFeature.objects.create(name="MUD CRACKS", code="MUD_CRACKS_TEST", category="sedimentary")
        elif feature.name != "MUD CRACKS":
            feature.name = "MUD CRACKS"
            feature.save(update_fields=["name"])
        media = Media.objects.create(
            media_location="uploads/pending/field-slip.png",
            ocr_data={
                "card_type": "field_slip",
                "field_slip": {
                    "field_number": {"interpreted": "FS-9"},
                    "verbatim_locality": {"interpreted": "Area 1"},
                    "verbatim_taxon": {"interpreted": "Homo"},
                    "verbatim_element": {"interpreted": "Femur"},
                    "accession_identification": {
                        "collection": {"interpreted": "KNM-LT 28567"},
                        "locality": {"interpreted": "LT"},
                        "accession_number": {"interpreted": "28567"},
                    },
                    "checkboxes": {
                        "sedimentary_features": [
                            {"source_label": "MUD CRACKS", "mark": "✔"},
                        ]
                    },
                },
            },
        )

        result = create_accessions_from_media(media)

        self.assertEqual(result["conflicts"], [])
        accession = Accession.objects.get()
        self.assertEqual(accession.collection.abbreviation, "KNM")
        self.assertEqual(accession.specimen_prefix.abbreviation, "LT")
        self.assertEqual(accession.specimen_no, 28567)
        self.assertTrue(Locality.objects.filter(abbreviation="LT").exists())
        link = AccessionFieldSlip.objects.get()
        self.assertEqual(link.accession, accession)
        self.assertEqual(link.fieldslip.field_number, "FS-9")
        self.assertQuerySetEqual(
            link.fieldslip.sedimentary_features.values_list("name", flat=True),
            ["MUD CRACKS"],
            transform=lambda x: x,
        )


class FieldSlipCardQCPrefillTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="qc_tester", password="pass")
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_qc_manager_bootstraps_field_slip_into_accession_payload(self):
        media = Media.objects.create(
            media_location="uploads/pending/field-slip-qc.png",
            ocr_data={
                "card_type": "field_slip",
                "field_slip": {
                    "field_number": {"interpreted": "FS-77"},
                    "collector": {"interpreted": "Leakey"},
                    "verbatim_taxon": {"interpreted": "Homo"},
                    "verbatim_element": {"interpreted": "Femur"},
                    "accession_identification": {
                        "collection": {"interpreted": "KNM-LT 28567"},
                        "locality": {"interpreted": "LT"},
                        "accession_number": {"interpreted": "28567"},
                    },
                },
            },
        )
        request = RequestFactory().get("/")
        request.user = self.user

        manager = MediaQCFormManager(request, media)

        self.assertEqual(len(manager.fieldslip_initial), 1)
        self.assertEqual(manager.fieldslip_initial[0]["field_number"], "FS-77")
        self.assertEqual(manager.fieldslip_initial[0]["collector"], "Leakey")
        self.assertTrue(manager.data.get("accessions"))
        self.assertEqual(
            manager.data["accessions"][0]["field_slips"][0]["field_number"]["interpreted"],
            "FS-77",
        )
