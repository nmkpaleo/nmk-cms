import pytest

from cms.management.commands.tooth_marking_debug import _normalize_detections
from cms.ocr_processing import _normalize_tooth_marking_detections as normalize_ocr_detections
from cms.services.review_approval import _normalize_tooth_marking_detections as normalize_review_detections


@pytest.mark.parametrize(
    "normalizer",
    [normalize_ocr_detections, normalize_review_detections],
)
def test_normalizers_filter_non_dict_and_non_serializable_entries(normalizer):
    payload = [
        {"token_raw": "Ml", "confidence": 0.9},
        "invalid",
        {"bad": {1, 2, 3}},
        {"nested": {"notation": "M1"}},
    ]

    result = normalizer(payload)

    assert result == [
        {"token_raw": "Ml", "confidence": 0.9},
        {"nested": {"notation": "M1"}},
    ]


def test_normalizers_return_empty_list_for_non_list_payloads():
    assert normalize_ocr_detections(None) == []
    assert normalize_ocr_detections({"a": 1}) == []
    assert normalize_review_detections(None) == []
    assert normalize_review_detections({"a": 1}) == []


def test_debug_normalizer_keeps_dicts_only():
    payload = [{"notation": "M1"}, 1, "x", {"notation": "P4"}]

    assert _normalize_detections(payload) == [{"notation": "M1"}, {"notation": "P4"}]
    assert _normalize_detections(None) == []
