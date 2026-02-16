from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from PIL import Image

from .base import ImageInput, ROI, TokenBox

try:  # pragma: no cover - import availability depends on deploy env
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


def is_tesseract_feature_enabled() -> bool:
    """Return whether the tesseract token-box backend is enabled by env flag."""

    return os.getenv("OCR_BOX_TESSERACT_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def is_tesseract_available() -> bool:
    """Return True when both pytesseract and the tesseract binary are present."""

    if pytesseract is None:
        return False

    tesseract_cmd = os.getenv("TESSERACT_CMD", "tesseract")
    return shutil.which(tesseract_cmd) is not None


class TesseractOCRBoxBackend:
    """OCR backend that extracts token boxes using Tesseract TSV output."""

    def get_token_boxes(
        self,
        image: ImageInput,
        *,
        roi: ROI | None = None,
    ) -> list[TokenBox]:
        if not is_tesseract_feature_enabled():
            return []
        if pytesseract is None:
            logger.warning("pytesseract is not installed; returning no OCR token boxes.")
            return []

        pil_image = _as_pil_image(image)
        x_offset = 0
        y_offset = 0
        if roi is not None:
            x1, y1, x2, y2 = _sanitize_roi(roi, pil_image.size)
            pil_image = pil_image.crop((x1, y1, x2, y2))
            x_offset = x1
            y_offset = y1

        try:
            data = pytesseract.image_to_data(
                pil_image,
                output_type=pytesseract.Output.DICT,
            )
        except pytesseract.TesseractNotFoundError:
            logger.warning("tesseract binary not found; returning no OCR token boxes.")
            return []

        if not isinstance(data, dict):
            return []

        texts = data.get("text") or []
        token_boxes: list[TokenBox] = []
        token_id = 0
        for index, raw_text in enumerate(texts):
            text = str(raw_text).strip()
            if not text:
                continue

            left = _to_int(_safe_get(data.get("left"), index))
            top = _to_int(_safe_get(data.get("top"), index))
            width = _to_int(_safe_get(data.get("width"), index))
            height = _to_int(_safe_get(data.get("height"), index))
            if width <= 0 or height <= 0:
                continue

            conf = _to_conf(_safe_get(data.get("conf"), index))
            block_id = _to_optional_int(_safe_get(data.get("block_num"), index))
            line_id = _to_optional_int(_safe_get(data.get("line_num"), index))

            token_boxes.append(
                TokenBox(
                    token_id=token_id,
                    text=text,
                    conf=conf,
                    x1=left + x_offset,
                    y1=top + y_offset,
                    x2=left + width + x_offset,
                    y2=top + height + y_offset,
                    line_id=line_id,
                    block_id=block_id,
                )
            )
            token_id += 1

        return token_boxes


def _as_pil_image(image: ImageInput) -> Image.Image:
    if isinstance(image, Image.Image):
        return image
    with Image.open(Path(image)) as opened:
        return opened.copy()


def _sanitize_roi(roi: ROI, size: tuple[int, int]) -> ROI:
    width, height = size
    x1, y1, x2, y2 = roi
    x1 = max(0, min(int(x1), width))
    y1 = max(0, min(int(y1), height))
    x2 = max(x1, min(int(x2), width))
    y2 = max(y1, min(int(y2), height))
    return x1, y1, x2, y2


def _safe_get(value: object, index: int) -> object | None:
    if isinstance(value, list) and index < len(value):
        return value[index]
    return None


def _to_int(value: object | None) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def _to_optional_int(value: object | None) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _to_conf(value: object | None) -> float | None:
    try:
        confidence = float(str(value))
    except (TypeError, ValueError):
        return None
    if confidence < 0:
        return None
    return confidence / 100 if confidence > 1 else confidence
