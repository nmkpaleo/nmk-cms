from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from cms.models import SpecimenListPage, SpecimenListPDF, SpecimenListRowCandidate
from cms.views import SpecimenListPageReviewView


class SpecimenListPageReviewViewTests(TestCase):
    def _build_pdf(self) -> SpecimenListPDF:
        pdf_file = SimpleUploadedFile("specimen.pdf", b"%PDF-1.4", content_type="application/pdf")
        return SpecimenListPDF.objects.create(
            source_label="Specimen List",
            original_filename="specimen.pdf",
            stored_file=pdf_file,
        )

    def test_save_row_formset_handles_new_rows_with_locked_columns(self):
        page = SpecimenListPage.objects.create(pdf=self._build_pdf(), page_number=1)
        view = SpecimenListPageReviewView()

        form = SimpleNamespace(
            cleaned_data={
                "row_id": None,
                "DELETE": False,
                "status": SpecimenListRowCandidate.ReviewStatus.EDITED,
                "accession_number": "ER 123",
                "tooth_marking_detections": [{"label": "A"}],
                "element_raw": "femur",
                "element_corrected": "Femur",
                "review_comment": "looks good",
                "red_dot": True,
                "green_dot": False,
                "data_json": None,
            }
        )

        view._save_row_formset(
            page,
            [form],
            [
                "accession_number",
                "tooth_marking_detections",
                "element_raw",
                "element_corrected",
            ],
        )

        row = SpecimenListRowCandidate.objects.get(page=page)
        self.assertEqual(row.data["accession_number"], "ER 123")
        self.assertIsNone(row.data["tooth_marking_detections"])
        self.assertIsNone(row.data["element_raw"])
        self.assertIsNone(row.data["element_corrected"])
        self.assertEqual(row.data["review_comment"], "looks good")
        self.assertTrue(row.data["red_dot"])
        self.assertFalse(row.data["green_dot"])
