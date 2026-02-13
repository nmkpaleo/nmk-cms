from types import SimpleNamespace
from unittest import TestCase
from unittest import mock

from PIL import Image

from cms.ocr_boxes.tesseract_boxes import TesseractOCRBoxBackend


class OCRBoxesTests(TestCase):
    def test_tesseract_backend_returns_non_empty_boxes(self):
        fake_pytesseract = SimpleNamespace(
            Output=SimpleNamespace(DICT="dict"),
            image_to_data=lambda image, output_type: {
                "text": ["M1", ""],
                "left": [10, 0],
                "top": [20, 0],
                "width": [30, 0],
                "height": [12, 0],
                "conf": [95, -1],
                "line_num": [2, 0],
                "block_num": [3, 0],
            },
        )

        with mock.patch("cms.ocr_boxes.tesseract_boxes.pytesseract", fake_pytesseract):
            with mock.patch.dict("os.environ", {"OCR_BOX_TESSERACT_ENABLED": "true"}, clear=False):
                boxes = TesseractOCRBoxBackend().get_token_boxes(Image.new("RGB", (200, 200), "white"))

        self.assertEqual(len(boxes), 1)
        box = boxes[0]
        self.assertEqual(box.token_id, 0)
        self.assertEqual(box.text, "M1")
        self.assertAlmostEqual(box.conf, 0.95, places=3)
        self.assertEqual((box.x1, box.y1, box.x2, box.y2), (10, 20, 40, 32))
        self.assertEqual(box.line_id, 2)
        self.assertEqual(box.block_id, 3)

    def test_tesseract_backend_roi_returns_page_coordinates(self):
        observed = {}

        def _image_to_data(image, output_type):
            observed["size"] = image.size
            return {
                "text": ["M2"],
                "left": [5],
                "top": [7],
                "width": [10],
                "height": [8],
                "conf": [88],
                "line_num": [1],
                "block_num": [1],
            }

        fake_pytesseract = SimpleNamespace(
            Output=SimpleNamespace(DICT="dict"),
            image_to_data=_image_to_data,
        )

        with mock.patch("cms.ocr_boxes.tesseract_boxes.pytesseract", fake_pytesseract):
            with mock.patch.dict("os.environ", {"OCR_BOX_TESSERACT_ENABLED": "true"}, clear=False):
                boxes = TesseractOCRBoxBackend().get_token_boxes(
                    Image.new("RGB", (500, 500), "white"),
                    roi=(100, 200, 180, 260),
                )

        self.assertEqual(observed["size"], (80, 60))
        self.assertEqual(len(boxes), 1)
        box = boxes[0]
        self.assertEqual((box.x1, box.y1, box.x2, box.y2), (105, 207, 115, 215))
