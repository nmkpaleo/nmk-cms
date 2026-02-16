"""Integration helper for tooth-marking correction with OCR token boxes."""

from __future__ import annotations

import logging
import os
from typing import Any

from cms.ocr_boxes.service import get_token_boxes, get_token_crops
from cms.tooth_markings.service import correct_element_text

logger = logging.getLogger(__name__)

_DEFAULT_MIN_CONFIDENCE = 0.85


def _min_confidence_from_env() -> float:
    raw = os.getenv("TOOTH_MARKING_MIN_CONF", str(_DEFAULT_MIN_CONFIDENCE)).strip()
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "Invalid TOOTH_MARKING_MIN_CONF value '%s'; using default %.2f",
            raw,
            _DEFAULT_MIN_CONFIDENCE,
        )
        return _DEFAULT_MIN_CONFIDENCE
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value


def _confidence_value(value: object) -> float | None:
    try:
        conf = float(str(value))
    except (TypeError, ValueError):
        return None
    if conf < 0:
        return None
    return conf


def _apply_confident_replacements(
    element_text: str,
    detections: list[dict[str, Any]],
    *,
    min_confidence: float,
) -> tuple[str, int]:
    replacements: list[dict[str, Any]] = []

    for detection in detections:
        start = detection.get("start")
        end = detection.get("end")
        notation = detection.get("notation")
        confidence = _confidence_value(detection.get("confidence"))

        if confidence is None or confidence < min_confidence:
            continue
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if not (0 <= start < end <= len(element_text)):
            continue
        if not isinstance(notation, str) or not notation:
            continue

        replacements.append({"start": start, "end": end, "value": notation})

    corrected = element_text
    for rep in sorted(replacements, key=lambda item: item["start"], reverse=True):
        corrected = corrected[: rep["start"]] + rep["value"] + corrected[rep["end"] :]

    return corrected, len(replacements)


def apply_tooth_marking_correction(
    page_image: Any,
    element_text: str,
    *,
    roi: tuple[int, int, int, int] | None = None,
) -> dict[str, Any]:
    """Apply tooth-marking correction using OCR token boxes.

    Returns deterministic keys and never raises, so callers can safely use this
    helper within OCR pipelines without disrupting ingestion.
    """

    raw_text = element_text or ""
    min_confidence = _min_confidence_from_env()

    result: dict[str, Any] = {
        "element_raw": raw_text,
        "element_corrected": raw_text,
        "detections": [],
        "replacements_applied": 0,
        "min_confidence": min_confidence,
        "error": None,
    }

    try:
        token_boxes = get_token_boxes(page_image, roi=roi)
        token_crops = get_token_crops(page_image, token_boxes)

        correction_payload = correct_element_text(raw_text, token_crops=token_crops)
        detections = correction_payload.get("detections")
        if not isinstance(detections, list):
            detections = []

        corrected_text, replacements_applied = _apply_confident_replacements(
            raw_text,
            [det for det in detections if isinstance(det, dict)],
            min_confidence=min_confidence,
        )

        result["detections"] = detections
        result["element_corrected"] = corrected_text
        result["replacements_applied"] = replacements_applied

        detections_count = int(len(detections))
        applied_count = int(replacements_applied)
        confidence_value = float(min_confidence)

        logger.info(
            "Tooth-marking correction completed.",
            extra={
                "detections": detections_count,
                "replacements_applied": applied_count,
                "min_confidence": confidence_value,
            },
        )
    except Exception as exc:  # pragma: no cover - defensive fallback path
        logger.warning("Tooth-marking correction failed; preserving raw element text: %s", exc)
        result["error"] = str(exc)

    return result
