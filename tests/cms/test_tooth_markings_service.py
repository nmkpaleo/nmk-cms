from __future__ import annotations

import sys
import types

from PIL import Image

from cms.tooth_markings.service import correct_element_text


def test_correct_element_text_without_crops_returns_unchanged_text() -> None:
    result = correct_element_text("Element m2 and p3")

    assert result["element_raw"] == "Element m2 and p3"
    assert result["element_corrected"] == "Element m2 and p3"
    assert result["detections"] == []


def test_correct_element_text_with_crops_rewrites_spans(monkeypatch) -> None:
    fake_chain = types.ModuleType("cms.tooth_markings.chain")

    def classify_token_image(_image):
        return "LM2", 0.93, {
            "jaw": {"label": "low", "prob": 0.95},
            "type": {"label": "M", "prob": 0.94},
            "index": {"label": "2", "prob": 0.93},
        }

    fake_chain.classify_token_image = classify_token_image
    monkeypatch.setitem(sys.modules, "cms.tooth_markings.chain", fake_chain)

    image = Image.new("RGB", (32, 32), color="white")
    result = correct_element_text(
        "Element m2",
        token_crops=[{"token": "m2", "image": image, "start": 8, "end": 10}],
    )

    assert result["element_corrected"] == "Element LM2"
    assert len(result["detections"]) == 1
    assert result["detections"][0]["notation"] == "LM2"
