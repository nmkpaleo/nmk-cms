from unittest import TestCase
from unittest import mock

from cms.tooth_markings import integration


class ToothMarkingIntegrationTests(TestCase):
    def test_apply_tooth_marking_correction_returns_deterministic_keys(self):
        with mock.patch.dict("os.environ", {"TOOTH_MARKING_MIN_CONF": "0.85"}, clear=False):
            with mock.patch.object(integration, "get_token_boxes", return_value=[object()]):
                with mock.patch.object(integration, "get_token_crops", return_value=[{"token": "Ml", "image": object()}]):
                    with mock.patch.object(
                        integration,
                        "correct_element_text",
                        return_value={
                            "element_raw": "Ml xx",
                            "element_corrected": "Ml xx",
                            "detections": [
                                {"start": 0, "end": 2, "notation": "M1", "confidence": 0.91},
                                {"start": 3, "end": 5, "notation": "M2", "confidence": 0.40},
                            ],
                        },
                    ):
                        result = integration.apply_tooth_marking_correction("dummy.png", "Ml xx")

        self.assertEqual(
            set(result.keys()),
            {
                "element_raw",
                "element_corrected",
                "detections",
                "replacements_applied",
                "min_confidence",
                "error",
            },
        )
        self.assertEqual(result["element_raw"], "Ml xx")
        self.assertEqual(result["element_corrected"], "M1 xx")
        self.assertEqual(result["replacements_applied"], 1)
        self.assertAlmostEqual(result["min_confidence"], 0.85, places=3)
        self.assertIsNone(result["error"])

    def test_apply_tooth_marking_correction_fallback_preserves_raw(self):
        with mock.patch.object(integration, "get_token_boxes", side_effect=RuntimeError("ocr failed")):
            result = integration.apply_tooth_marking_correction("dummy.png", "M1")

        self.assertEqual(result["element_raw"], "M1")
        self.assertEqual(result["element_corrected"], "M1")
        self.assertEqual(result["detections"], [])
        self.assertEqual(result["replacements_applied"], 0)
        self.assertEqual(result["error"], "ocr failed")
