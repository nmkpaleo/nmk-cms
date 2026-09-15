from dataclasses import dataclass
from pathlib import Path

import pytest
from django.test import override_settings

pytestmark = pytest.mark.django_db

from cms.ocr_processing import (
    InsufficientQuotaError,
    OCRTimeoutError,
    _clean_string,
    _generate_unknown_field_number,
    _has_any_nature_data,
    _has_identification_data,
    _has_nature_data,
    _load_first_json_object,
    _make_html_key,
    _mark_scan_failed,
    _parse_collection_date_value,
    _parse_row_extraction_payload,
    _resolve_lookup_names,
    process_pending_scans,
)


def test_parse_row_extraction_payload_validates_rows_and_columns_types():
    parsed = _parse_row_extraction_payload({"columns_detected": ["a"], "rows": [{"x": 1}, "bad"]})
    assert parsed == {"columns_detected": ["a"], "rows": [{"x": 1}]}

    with pytest.raises(ValueError, match="columns_detected"):
        _parse_row_extraction_payload({"columns_detected": "nope", "rows": []})

    with pytest.raises(ValueError, match="rows"):
        _parse_row_extraction_payload({"columns_detected": [], "rows": "nope"})


def test_load_first_json_object_parses_first_object_and_rejects_non_object():
    payload = _load_first_json_object('  {"k": 1} trailing text')
    assert payload["k"] == 1

    with pytest.raises(ValueError, match="JSON object"):
        _load_first_json_object("[1,2,3]")


def test_clean_string_and_date_parsing_helpers():
    assert _clean_string("  abc  ") == "abc"
    assert _clean_string(r"\N") == r"\N"
    assert _clean_string(None) is None

    parsed = _parse_collection_date_value("2024-01-31")
    assert parsed is not None and parsed.isoformat() == "2024-01-31"
    assert _parse_collection_date_value("not-a-date") is None


def test_identification_and_nature_data_predicates_and_unknown_field_number():
    assert _has_identification_data({"taxon": {"interpreted": "Homo"}}) is True
    assert _has_identification_data({"taxon": {"interpreted": ""}}) is True

    assert _has_nature_data({"element_name": {"interpreted": "Femur"}}) is True
    assert _has_nature_data({"element_name": {"interpreted": ""}}) is True

    assert _has_any_nature_data([{"element_name": {"interpreted": ""}}, {"side": {"interpreted": "left"}}]) is True
    generated = _generate_unknown_field_number()
    assert generated.startswith("UNKNOWN FIELD NUMBER #")


def test_make_html_key_deduplicates_and_normalizes():
    used = set()
    first = _make_html_key("Field Number", used)
    second = _make_html_key("Field Number", used)
    assert first == "Field_Number"
    assert second == "Field_Number_2"


def test_resolve_lookup_names_matches_name_and_code(monkeypatch):
    @dataclass(eq=True, frozen=True)
    class Obj:
        name: str
        code: str

    class _Query:
        def __init__(self, items):
            self.items = items

        def first(self):
            return self.items[0] if self.items else None

    class _Manager:
        def __init__(self, objs):
            self._objs = objs

        def filter(self, **kwargs):
            if "name__iexact" in kwargs:
                name = kwargs["name__iexact"].lower()
                return _Query([o for o in self._objs if o.name.lower() == name])
            if "code__iexact" in kwargs:
                code = kwargs["code__iexact"].lower()
                return _Query([o for o in self._objs if o.code.lower() == code])
            return _Query([])

    class _Model:
        code = True
        objects = _Manager([Obj("SILT", "SILT"), Obj("MUD CRACKS", "MUD_CRACKS")])

    resolved = _resolve_lookup_names(_Model, ["silt", "mud cracks", "unknown"]) 
    assert len(resolved) == 2


class _FakeMedia:
    class OCRStatus:
        FAILED = "failed"

    def __init__(self):
        self.media_location = type("M", (), {"name": "uploads/pending/a.jpg"})()
        self.ocr_status = None
        self.ocr_data = None
        self.saved = False

    def save(self, **_kwargs):
        self.saved = True


def test_mark_scan_failed_moves_file_and_updates_media(tmp_path):
    media_root = tmp_path
    pending = media_root / "uploads" / "pending"
    failed = media_root / "uploads" / "failed"
    pending.mkdir(parents=True)
    path = pending / "a.jpg"
    path.write_bytes(b"x")

    media = _FakeMedia()
    with override_settings(MEDIA_ROOT=str(media_root)):
        _mark_scan_failed(media, path, failed, Exception("boom"))

    assert (failed / "a.jpg").exists()
    assert media.ocr_status == media.OCRStatus.FAILED
    assert media.saved is True


def test_process_pending_scans_handles_timeout_quota_and_generic_failure(monkeypatch, tmp_path):
    media_root = tmp_path
    pending = media_root / "uploads" / "pending"
    pending.mkdir(parents=True)
    file_a = pending / "a.jpg"
    file_b = pending / "b.jpg"
    file_c = pending / "c.jpg"
    for f in (file_a, file_b, file_c):
        f.write_bytes(b"x")

    media = _FakeMedia()

    class _FilterResult:
        def first(self):
            return media

    class _Manager:
        def filter(self, **_kwargs):
            return _FilterResult()

    class _Media:
        objects = _Manager()

    calls = {"count": 0}

    def _proc(_media, path, _ocr_dir):
        calls["count"] += 1
        if path.name == "a.jpg":
            raise OCRTimeoutError("timeout")
        if path.name == "b.jpg":
            raise InsufficientQuotaError("quota")
        raise RuntimeError("fail")

    marked = []

    def _mark(_media, path, _failed_dir, _exc):
        marked.append(path.name)

    monkeypatch.setattr("cms.ocr_processing.Media", _Media)
    monkeypatch.setattr("cms.ocr_processing._process_single_scan", _proc)
    monkeypatch.setattr("cms.ocr_processing._mark_scan_failed", _mark)

    with override_settings(MEDIA_ROOT=str(media_root)):
        successes, failures, total, errors, jammed, processed, insufficient = process_pending_scans(limit=1)

    assert successes == 0
    assert failures == 1
    assert total == 1
    assert jammed == "a.jpg"
    assert processed == ["a.jpg"]
    assert insufficient is False
    assert marked == ["a.jpg"]
    assert any("timed out" in e for e in errors)
