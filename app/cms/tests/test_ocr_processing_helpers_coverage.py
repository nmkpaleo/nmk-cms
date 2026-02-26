from cms.ocr_processing import (
    _expand_row_suffixes,
    _is_insufficient_quota_error,
    _normalize_label,
    _normalize_tooth_marking_detections,
    _normalise_boolean,
    _strip_code_fences,
    _value_interpreted,
    make_interpreted_value,
    normalize_fragments_value,
)


class _Err:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __str__(self):
        return self.__dict__.get("message", "")


def test_make_interpreted_value_variants():
    assert make_interpreted_value(None) == {}
    assert make_interpreted_value("X")["interpreted"] == "X"
    payload = make_interpreted_value("X", raw="raw", confidence=0.5)
    assert payload == {"interpreted": "X", "raw": "raw", "confidence": 0.5}


def test_normalize_tooth_marking_detections_filters_invalid_entries():
    data = [{"a": 1}, "bad", {"b": [1, 2]}]
    result = _normalize_tooth_marking_detections(data)
    assert result == [{"a": 1}, {"b": [1, 2]}]


def test_is_insufficient_quota_error_detects_multiple_shapes():
    assert _is_insufficient_quota_error(_Err(code="insufficient_quota")) is True
    assert _is_insufficient_quota_error(_Err(error={"code": "insufficient_quota"})) is True
    assert _is_insufficient_quota_error(_Err(response={"error": {"type": "insufficient_quota"}})) is True
    assert _is_insufficient_quota_error(_Err(message="exceeded your current quota")) is True
    assert _is_insufficient_quota_error(_Err(message="something else")) is False


def test_strip_code_fences_and_boolean_normalization():
    content = "```json\n{\"a\": 1}\n```"
    assert _strip_code_fences(content).strip() == '{"a": 1}'
    assert _normalise_boolean("yes") is True
    assert _normalise_boolean("0") is False


def test_value_interpreted_and_normalizers():
    assert _value_interpreted({"interpreted": "A", "raw": "B"}) == "A"
    assert _value_interpreted({"interpreted": "", "raw": "B"}) == "B"
    assert _value_interpreted("X") == "X"
    assert _normalize_label("  root/bur ") == "ROOT/BUR"
    assert normalize_fragments_value({"interpreted": "12"}) == 12
    assert normalize_fragments_value({"interpreted": "x"}) is None


def test_expand_row_suffixes_with_ranges_and_invalid_tokens():
    suffixes = _expand_row_suffixes({"interpreted": "A-C, B, invalid@"})
    assert suffixes == ["A", "B", "C"]
