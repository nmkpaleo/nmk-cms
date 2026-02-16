"""Public service API for correcting element/nature text tooth markings."""

from __future__ import annotations

from typing import Any, Dict, List

from .rewrite import find_suspects, rewrite_with_crops


def correct_element_text(element_text: str, token_crops: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """Correct tooth-like tokens in element text using optional token crops.

    If token_crops is omitted, no model inference is run yet (bounding boxes are integrated later).
    """
    if token_crops is None:
        # Placeholder mode requested for now: detect suspects but do not alter text.
        _ = find_suspects(element_text)
        return {
            "element_raw": element_text,
            "element_corrected": element_text,
            "detections": [],
        }
    return rewrite_with_crops(element_text, token_crops)
