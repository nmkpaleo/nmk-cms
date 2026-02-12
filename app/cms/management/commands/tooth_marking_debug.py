from __future__ import annotations

import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from cms.ocr_boxes.service import get_token_boxes
from cms.tooth_markings.integration import apply_tooth_marking_correction


class Command(BaseCommand):
    help = "Debug tooth-marking correction on a single page image and element text."

    def add_arguments(self, parser):
        parser.add_argument("--image", required=True, help="Path to source page image.")
        parser.add_argument("--text", required=True, help="Element text to correct (raw OCR text).")
        parser.add_argument(
            "--roi",
            default=None,
            help="Optional ROI as x1,y1,x2,y2 in page coordinates.",
        )
        parser.add_argument(
            "--overlay-out",
            default=None,
            help="Optional output image path to save debug overlay with token boxes.",
        )
        parser.add_argument(
            "--min-confidence",
            type=float,
            default=None,
            help="Optional override for TOOTH_MARKING_MIN_CONF during this run.",
        )

    def handle(self, *args, **options):
        image_path = Path(options["image"]).expanduser()
        if not image_path.exists() or not image_path.is_file():
            raise CommandError(f"Image path does not exist or is not a file: {image_path}")

        roi = self._parse_roi(options.get("roi"))

        env_backup: str | None = None
        min_conf = options.get("min_confidence")
        if min_conf is not None:
            env_backup = os.environ.get("TOOTH_MARKING_MIN_CONF")
            os.environ["TOOTH_MARKING_MIN_CONF"] = str(min_conf)

        try:
            correction = apply_tooth_marking_correction(str(image_path), options["text"], roi=roi)
            token_boxes = get_token_boxes(str(image_path), roi=roi)
        finally:
            if min_conf is not None:
                if env_backup is None:
                    os.environ.pop("TOOTH_MARKING_MIN_CONF", None)
                else:
                    os.environ["TOOTH_MARKING_MIN_CONF"] = env_backup

        self.stdout.write("Tooth-marking debug result")
        self.stdout.write(f"- image: {image_path}")
        self.stdout.write(f"- roi: {roi if roi else 'full page'}")
        self.stdout.write(f"- token_boxes: {len(token_boxes)}")
        self.stdout.write(f"- raw: {correction.get('element_raw', '')}")
        self.stdout.write(f"- corrected: {correction.get('element_corrected', '')}")
        self.stdout.write(f"- replacements_applied: {correction.get('replacements_applied', 0)}")
        self.stdout.write(f"- min_confidence: {correction.get('min_confidence')}")
        if correction.get("error"):
            self.stdout.write(self.style.WARNING(f"- error: {correction['error']}"))

        detections = correction.get("detections")
        if not isinstance(detections, list):
            detections = []

        self.stdout.write("Detection summary:")
        if not detections:
            self.stdout.write("  (none)")
        else:
            for idx, detection in enumerate(detections, start=1):
                if not isinstance(detection, dict):
                    self.stdout.write(f"  {idx}. {detection}")
                    continue
                notation = detection.get("notation")
                conf = detection.get("confidence")
                token_raw = detection.get("token_raw")
                span = (detection.get("start"), detection.get("end"))
                self.stdout.write(
                    f"  {idx}. token={token_raw!r} notation={notation!r} "
                    f"confidence={conf!r} span={span}"
                )

        overlay_out = options.get("overlay_out")
        if overlay_out:
            self._write_overlay(
                image_path=image_path,
                output_path=Path(overlay_out).expanduser(),
                token_boxes=token_boxes,
                detections=detections,
                roi=roi,
            )

    def _parse_roi(self, raw: str | None) -> tuple[int, int, int, int] | None:
        if not raw:
            return None
        parts = [part.strip() for part in raw.split(",")]
        if len(parts) != 4:
            raise CommandError("ROI must be in the form x1,y1,x2,y2")
        try:
            x1, y1, x2, y2 = [int(part) for part in parts]
        except ValueError as exc:
            raise CommandError("ROI values must be integers") from exc
        if x2 <= x1 or y2 <= y1:
            raise CommandError("ROI must satisfy x2>x1 and y2>y1")
        return x1, y1, x2, y2

    def _write_overlay(self, *, image_path: Path, output_path: Path, token_boxes, detections, roi):
        from PIL import Image, ImageDraw

        image = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(image)

        detection_tokens = {
            str(det.get("token_raw"))
            for det in detections
            if isinstance(det, dict) and det.get("token_raw")
        }

        for box in token_boxes:
            color = "lime" if box.text in detection_tokens else "yellow"
            draw.rectangle([(box.x1, box.y1), (box.x2, box.y2)], outline=color, width=2)

        if roi:
            draw.rectangle([(roi[0], roi[1]), (roi[2], roi[3])], outline="red", width=3)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)
        self.stdout.write(self.style.SUCCESS(f"Saved overlay image: {output_path}"))
