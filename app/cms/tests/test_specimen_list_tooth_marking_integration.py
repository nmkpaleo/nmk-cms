import json
import uuid
from unittest import mock

from crum import set_current_user
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from cms.models import (
    Collection,
    Element,
    Locality,
    NatureOfSpecimen,
    SpecimenListPage,
    SpecimenListPDF,
    SpecimenListRowCandidate,
)
from cms.services.review_approval import approve_page, approve_row


class SpecimenListToothMarkingIntegrationTests(TestCase):
    def _build_pdf(self) -> SpecimenListPDF:
        pdf_file = SimpleUploadedFile("specimen.pdf", b"%PDF-1.4", content_type="application/pdf")
        return SpecimenListPDF.objects.create(
            source_label="Specimen List",
            original_filename="specimen.pdf",
            stored_file=pdf_file,
        )

    def _build_reviewer(self):
        return get_user_model().objects.create(username=f"reviewer-{uuid.uuid4().hex}")

    def _ensure_collection_and_locality(self, user) -> None:
        set_current_user(user)
        try:
            Collection.objects.get_or_create(
                abbreviation="KNM",
                defaults={"description": "Kenya National Museums"},
            )
            Locality.objects.get_or_create(
                abbreviation="ER",
                defaults={"name": "East Rudolf"},
            )
            Element.objects.get_or_create(name="M1")
        finally:
            set_current_user(None)

    def test_approve_row_persists_corrected_element_and_detections(self):
        reviewer = self._build_reviewer()
        self._ensure_collection_and_locality(reviewer)
        pdf = self._build_pdf()
        page = SpecimenListPage.objects.create(pdf=pdf, page_number=1)
        specimen_no = uuid.uuid4().int % 1000000

        row = SpecimenListRowCandidate.objects.create(
            page=page,
            row_index=0,
            data={
                "accession_number": f"KNM-ER {specimen_no}",
                "taxon": "Homo",
                "element": "Ml",
            },
        )

        with mock.patch(
            "cms.services.review_approval.apply_tooth_marking_correction",
            return_value={
                "element_raw": "Ml",
                "element_corrected": "M1",
                "detections": [{"token_raw": "Ml", "notation": "M1", "confidence": 0.91}],
                "replacements_applied": 1,
                "min_confidence": 0.85,
                "error": None,
            },
        ):
            result = approve_row(row=row, reviewer=reviewer)

        self.assertEqual(result.errors, [])

        row.refresh_from_db()
        draft_data = ((row.data or {}).get("_draft") or {}).get("data") or {}
        self.assertEqual(draft_data.get("element_raw"), "Ml")
        self.assertEqual(draft_data.get("element_corrected"), "M1")
        self.assertIsInstance(draft_data.get("tooth_marking_detections"), list)

        nature = NatureOfSpecimen.objects.get(accession_row__accession__specimen_no=specimen_no)
        self.assertEqual(nature.verbatim_element, "M1")
        self.assertEqual(nature.verbatim_element_raw, "Ml")
        self.assertEqual(
            nature.tooth_marking_detections,
            [{"token_raw": "Ml", "notation": "M1", "confidence": 0.91}],
        )

    def test_approve_page_reports_page_row_numbers_for_invalid_accessions(self):
        reviewer = self._build_reviewer()
        self._ensure_collection_and_locality(reviewer)
        pdf = self._build_pdf()
        page = SpecimenListPage.objects.create(pdf=pdf, page_number=1)

        SpecimenListRowCandidate.objects.create(
            page=page,
            row_index=0,
            data={"accession_number": "KNMX-SO 3146", "taxon": "Homo"},
        )
        SpecimenListRowCandidate.objects.create(
            page=page,
            row_index=1,
            data={"accession_number": "KNM-ER 1234", "taxon": "Homo"},
        )

        with self.assertRaises(ValidationError) as exc:
            approve_page(page=page, reviewer=reviewer)

        message = str(exc.exception)
        self.assertIn("rows 1", message)
        self.assertIn("row 1:", message)
        self.assertIn("KNM, KNMI, KNMP", message)

