from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from PIL import Image

from .base import ImageInput, ROI, TokenBox

logger = logging.getLogger(__name__)


def is_paddle_engine_enabled() -> bool:
    """Return True when OCR_BOX_ENGINE explicitly selects paddle."""

    return os.getenv("OCR_BOX_ENGINE", "").strip().lower() == "paddle"


class PaddleOCRBoxBackend:
    """Optional token-box backend powered by PaddleOCR.

    The backend lazy-loads PaddleOCR and only initializes it when
    ``OCR_BOX_ENGINE=paddle``. If PaddleOCR cannot be imported or instantiated,
    the backend logs a warning and returns no boxes.
    """

    def __init__(self) -> None:
        self._ocr_instance: Any | None = None
        self._init_attempted = False

    def get_token_boxes(
        self,
        image: ImageInput,
        *,
        roi: ROI | None = None,
    ) -> list[TokenBox]:
        if not is_paddle_engine_enabled():
            return []

        ocr = self._get_ocr_instance()
        if ocr is None:
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
            # PaddleOCR accepts numpy arrays.
            import numpy as np

            result = ocr.ocr(np.array(pil_image), cls=False)
        except Exception as exc:
            logger.warning(
                "PaddleOCR runtime failed; returning no OCR token boxes. Error: %s",
                exc,
            )
            return []

        boxes: list[TokenBox] = []
        token_id = 0
        for line in _iter_result_lines(result):
            for item in line:
                token = _build_token_from_item(item, token_id, x_offset=x_offset, y_offset=y_offset)
                if token is None:
                    continue
                boxes.append(token)
                token_id += 1

        return boxes

    def _get_ocr_instance(self) -> Any | None:
        if self._ocr_instance is not None:
            return self._ocr_instance
        if self._init_attempted:
            return None

        self._init_attempted = True
        try:
            from paddleocr import PaddleOCR

            self._ocr_instance = PaddleOCR(use_angle_cls=False, lang="en")
            return self._ocr_instance
        except Exception as exc:
            logger.warning(
                "PaddleOCR is unavailable; falling back to empty OCR token boxes. Error: %s",
                exc,
            )
            return None


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


def _iter_result_lines(result: Any) -> list[list[Any]]:
    if not isinstance(result, list):
        return []
    # Depending on PaddleOCR version, result shape can be [ [line,...] ] for one image.
    if len(result) == 1 and isinstance(result[0], list):
        first = result[0]
        if first and isinstance(first[0], list):
            return first
    return [line for line in result if isinstance(line, list)]


def _build_token_from_item(
    item: Any,
    token_id: int,
    *,
    x_offset: int,
    y_offset: int,
) -> TokenBox | None:
    if not isinstance(item, list) or len(item) != 2:
        return None

    points, payload = item
    if not isinstance(points, list) or len(points) < 4:
        return None

    text: str | None = None
    conf: float | None = None
    if isinstance(payload, (list, tuple)) and len(payload) >= 1:
        text = str(payload[0]).strip()
        if len(payload) > 1:
            try:
                conf = float(payload[1])
            except (TypeError, ValueError):
                conf = None

    if not text:
        return None

    xs: list[int] = []
    ys: list[int] = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            continue
        try:
            x = int(float(point[0]))
            y = int(float(point[1]))
        except (TypeError, ValueError):
            continue
        xs.append(x)
        ys.append(y)

    if not xs or not ys:
        return None

    return TokenBox(
        token_id=token_id,
        text=text,
        conf=conf,
        x1=min(xs) + x_offset,
        y1=min(ys) + y_offset,
        x2=max(xs) + x_offset,
        y2=max(ys) + y_offset,
    )
