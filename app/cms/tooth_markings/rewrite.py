"""Helpers to detect and rewrite tooth-like tokens in element text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from PIL import Image

SUSPECT_TOKEN_RE = re.compile(
    r"\b(?:[iImMpPcCdD][0-4]?|[lLuU]?[iImMpPcC][0-4]|[dD]\d{1,2})\b"
)


@dataclass(frozen=True)
class SuspectToken:
    token: str
    start: int
    end: int


def find_suspects(element_text: str) -> List[SuspectToken]:
    """Find permissive tooth-like token candidates in free text."""
    return [
        SuspectToken(token=m.group(0), start=m.start(), end=m.end())
        for m in SUSPECT_TOKEN_RE.finditer(element_text)
    ]


def _coerce_image(image_like: Any) -> Image.Image:
    if isinstance(image_like, Image.Image):
        return image_like
    if isinstance(image_like, str):
        return Image.open(image_like)
    raise TypeError("token crop image must be PIL.Image.Image or file path string")


def rewrite_with_crops(element_text: str, token_crops: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Classify provided token crops and rewrite text spans.

    Each crop should include at least `image`, and usually `start` and `end`.
    """
    from .chain import classify_token_image

    detections: List[Dict[str, Any]] = []
    replacements: List[Dict[str, Any]] = []

    for crop in token_crops:
        image = _coerce_image(crop["image"])
        notation, confidence, parts = classify_token_image(image)

        start = crop.get("start")
        end = crop.get("end")
        token_raw = crop.get("token", "")
        detection = {
            "token_raw": token_raw,
            "notation": notation,
            "confidence": confidence,
            "parts": parts,
            "start": start,
            "end": end,
        }
        detections.append(detection)

        if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(element_text):
            replacements.append({"start": start, "end": end, "value": notation})

    corrected = element_text
    for rep in sorted(replacements, key=lambda item: item["start"], reverse=True):
        corrected = corrected[: rep["start"]] + rep["value"] + corrected[rep["end"] :]

    return {
        "element_raw": element_text,
        "element_corrected": corrected,
        "detections": detections,
    }
