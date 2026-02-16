from types import SimpleNamespace
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from cms.models import SpecimenListPage, SpecimenListPageOCR, SpecimenListPDF
from cms.ocr_processing import run_specimen_list_raw_ocr


def _build_openai_response(payload):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=payload))],
        model="gpt-4o",
        id="resp_123",
    )


def _build_openai_client(response):
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: response,
            ),
        ),
    )


class SpecimenListRawOCRTests(TestCase):
    def setUp(self):
        pdf_file = SimpleUploadedFile("specimen.pdf", b"%PDF-1.4", content_type="application/pdf")
        self.pdf = SpecimenListPDF.objects.create(
            source_label="Specimen List",
            original_filename="specimen.pdf",
            stored_file=pdf_file,
        )
        self.page = SpecimenListPage.objects.create(pdf=self.pdf, page_number=1)
        image_file = SimpleUploadedFile("page.png", b"fake-image-data", content_type="image/png")
        self.page.image_file.save("page.png", image_file, save=True)

    def test_run_specimen_list_raw_ocr_creates_entry(self):
        payload = {
            "raw_text": "Line 1\nLine 2",
            "bounding_boxes": [
                {"text": "Line 1", "x": 1, "y": 2, "width": 3, "height": 4, "confidence": 0.9},
            ],
        }
        response = _build_openai_response(payload=str(payload).replace("'", '"'))
        with mock.patch(
            "cms.ocr_processing.get_openai_client",
            return_value=_build_openai_client(response),
        ):
            entry = run_specimen_list_raw_ocr(self.page, max_retries=1)

        self.assertIsInstance(entry, SpecimenListPageOCR)
        self.assertEqual(entry.page_id, self.page.id)
        self.assertEqual(entry.raw_text, "Line 1\nLine 2")
        self.assertEqual(entry.bounding_boxes, payload["bounding_boxes"])

    def test_run_specimen_list_raw_ocr_is_idempotent(self):
        existing = SpecimenListPageOCR.objects.create(
            page=self.page,
            raw_text="Existing OCR",
            bounding_boxes=[],
            ocr_engine="chatgpt-vision",
        )

        with mock.patch(
            "cms.ocr_processing.get_openai_client",
            side_effect=AssertionError("OpenAI client should not be called for existing OCR entries."),
        ):
            entry = run_specimen_list_raw_ocr(self.page, max_retries=1)

        self.assertEqual(entry.id, existing.id)

    def test_run_specimen_list_raw_ocr_failure_does_not_create_entry(self):
        def _raise_error(**kwargs):
            raise RuntimeError("OCR failed")

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_raise_error)))
        with mock.patch("cms.ocr_processing.get_openai_client", return_value=client):
            with self.assertRaises(RuntimeError):
                run_specimen_list_raw_ocr(self.page, max_retries=1)

        self.assertEqual(SpecimenListPageOCR.objects.filter(page=self.page).count(), 0)
