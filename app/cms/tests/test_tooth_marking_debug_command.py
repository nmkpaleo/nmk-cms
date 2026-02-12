from __future__ import annotations

import tempfile
from io import StringIO
from pathlib import Path
from unittest import TestCase, mock

from django.core.management import call_command
from PIL import Image

from cms.ocr_boxes.base import TokenBox


class ToothMarkingDebugCommandTests(TestCase):
    def test_command_prints_raw_corrected_and_detection_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "input.png"
            Image.new("RGB", (120, 90), "white").save(image_path)

            out = StringIO()
            with mock.patch(
                "cms.management.commands.tooth_marking_debug.apply_tooth_marking_correction",
                return_value={
                    "element_raw": "Ml",
                    "element_corrected": "M1",
                    "detections": [
                        {
                            "token_raw": "Ml",
                            "notation": "M1",
                            "confidence": 0.92,
                            "start": 0,
                            "end": 2,
                        }
                    ],
                    "replacements_applied": 1,
                    "min_confidence": 0.85,
                    "error": None,
                },
            ):
                with mock.patch(
                    "cms.management.commands.tooth_marking_debug.get_token_boxes",
                    return_value=[
                        TokenBox(
                            token_id=0,
                            text="Ml",
                            conf=0.92,
                            x1=10,
                            y1=12,
                            x2=30,
                            y2=24,
                        )
                    ],
                ):
                    call_command(
                        "tooth_marking_debug",
                        image=str(image_path),
                        text="Ml",
                        stdout=out,
                    )

            rendered = out.getvalue()
            self.assertIn("raw: Ml", rendered)
            self.assertIn("corrected: M1", rendered)
            self.assertIn("Detection summary", rendered)
            self.assertIn("token='Ml' notation='M1'", rendered)

    def test_command_can_save_overlay_image(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "input.png"
            overlay_path = Path(tmpdir) / "overlay.png"
            Image.new("RGB", (120, 90), "white").save(image_path)

            out = StringIO()
            with mock.patch(
                "cms.management.commands.tooth_marking_debug.apply_tooth_marking_correction",
                return_value={
                    "element_raw": "Ml",
                    "element_corrected": "M1",
                    "detections": [{"token_raw": "Ml", "notation": "M1", "confidence": 0.92}],
                    "replacements_applied": 1,
                    "min_confidence": 0.85,
                    "error": None,
                },
            ):
                with mock.patch(
                    "cms.management.commands.tooth_marking_debug.get_token_boxes",
                    return_value=[
                        TokenBox(
                            token_id=0,
                            text="Ml",
                            conf=0.92,
                            x1=10,
                            y1=12,
                            x2=30,
                            y2=24,
                        )
                    ],
                ):
                    call_command(
                        "tooth_marking_debug",
                        image=str(image_path),
                        text="Ml",
                        overlay_out=str(overlay_path),
                        stdout=out,
                    )

            self.assertTrue(overlay_path.exists())
            self.assertIn("Saved overlay image", out.getvalue())
