from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from cms.utils import coerce_stripped, normalise_yes_no, select_current_identification


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, None),
        ("", None),
        ("  ", None),
        ("\\N", None),
        ("  abc  ", "abc"),
        (123, "123"),
    ],
)
def test_coerce_stripped_normalizes_empty_and_trimmed_values(value, expected):
    assert coerce_stripped(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, False),
        ("", False),
        ("YES", True),
        ("true", True),
        ("1", True),
        ("y", True),
        ("t", True),
        ("no", False),
        ("0", False),
    ],
)
def test_normalise_yes_no_accepts_common_truthy_tokens(value, expected):
    assert normalise_yes_no(value) is expected


def _identification(*, primary_key, created_on, date_identified=None, reference_year=""):
    return SimpleNamespace(
        pk=primary_key,
        created_on=created_on,
        date_identified=date_identified,
        reference=SimpleNamespace(year=reference_year) if reference_year else None,
    )


def test_current_identification_prefers_latest_identification_date():
    older_dated = _identification(
        primary_key=1, created_on=datetime(2025, 1, 3, tzinfo=timezone.utc),
        date_identified=date(2023, 1, 1),
    )
    latest_dated = _identification(
        primary_key=2, created_on=datetime(2024, 1, 1, tzinfo=timezone.utc),
        date_identified=date(2024, 1, 1),
    )
    undated_newer_reference = _identification(
        primary_key=3, created_on=datetime(2026, 1, 1, tzinfo=timezone.utc), reference_year="2025",
    )

    assert select_current_identification([older_dated, undated_newer_reference, latest_dated]) is latest_dated


def test_current_identification_uses_reference_year_then_database_recency():
    old_reference = _identification(
        primary_key=1, created_on=datetime(2026, 1, 1, tzinfo=timezone.utc), reference_year="1999",
    )
    new_reference = _identification(
        primary_key=2, created_on=datetime(2024, 1, 1, tzinfo=timezone.utc), reference_year="2005",
    )
    newest_database_record = _identification(
        primary_key=3, created_on=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert select_current_identification([old_reference, newest_database_record, new_reference]) is new_reference
    assert select_current_identification([old_reference, newest_database_record]) is old_reference
