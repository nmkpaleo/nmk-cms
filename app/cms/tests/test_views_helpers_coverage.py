from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from cms.views import (
    _coerce_decimal,
    _compute_expected_total,
    _form_order_value,
    _form_row_id,
    _ident_payload_has_explicit_fields,
    _natures_payload_has_meaningful_data,
    _parse_ocr_limit,
    _set_interpreted,
    _should_loop,
    _split_csv_tokens,
)


class _Field:
    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value


class _FakeForm:
    def __init__(self, row_id=None, order=None, initial=None):
        self._fields = {"row_id": _Field(row_id), "order": _Field(order)}
        self.initial = initial or {}

    def __getitem__(self, key):
        return self._fields[key]


def test_should_loop_and_parse_ocr_limit_behaviour():
    req = SimpleNamespace(GET={"loop": "yes", "limit": "25"})
    assert _should_loop(req) is True
    assert _parse_ocr_limit(req) == 25

    req = SimpleNamespace(GET={"loop": "no", "limit": "-1"})
    assert _should_loop(req) is False
    assert _parse_ocr_limit(req) is None


def test_compute_expected_total_honours_limit():
    assert _compute_expected_total(attempted=1, remaining=5, limit=None) == 6
    assert _compute_expected_total(attempted=1, remaining=9, limit=3) == 3
    assert _compute_expected_total(attempted=5, remaining=9, limit=3) == 5


def test_coerce_decimal_falls_back_to_zero():
    assert _coerce_decimal(None) == Decimal("0")
    assert _coerce_decimal("") == Decimal("0")
    assert _coerce_decimal("2.5") == Decimal("2.5")
    assert _coerce_decimal("nope") == Decimal("0")


def test_split_csv_tokens_and_payload_checks():
    assert _split_csv_tokens("A, B, A") == ["A", "B"]
    assert _split_csv_tokens(["a", " ", "b"]) == ["a", "b"]
    assert _ident_payload_has_explicit_fields({"taxon": {"interpreted": "Homo"}}) is True
    assert _ident_payload_has_explicit_fields({}) is False


def test_natures_payload_meaningful_data_detects_interpreted_values():
    natures = [{"element_name": {"interpreted": "Femur"}}]
    assert _natures_payload_has_meaningful_data(natures) is True
    assert _natures_payload_has_meaningful_data([{"element_name": {"interpreted": ""}}]) is False


def test_set_interpreted_normalizes_date_and_blank_strings():
    container = {}
    _set_interpreted(container, "date", date(2024, 1, 2))
    assert container["date"]["interpreted"] == "2024-01-02"
    _set_interpreted(container, "text", "  ")
    assert container["text"]["interpreted"] is None


def test_form_row_id_and_order_value_use_initial_fallbacks():
    form = _FakeForm(row_id=None, order=None, initial={"row_id": 7, "order": "12"})
    assert _form_row_id(form) == "7"
    assert _form_order_value(form) == 12

    form = _FakeForm(row_id="", order="bad")
    assert _form_row_id(form) == ""
    assert _form_order_value(form) == 0
