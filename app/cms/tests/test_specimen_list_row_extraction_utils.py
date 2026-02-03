import pytest

from cms.utils import apply_ditto_marks, is_ditto_mark


@pytest.mark.parametrize(
    "value",
    [
        "″",
        "”",
        "〃",
        "\"",
        "''",
        "!!",
        "11",
        "((",
        "))",
    ],
)
def test_is_ditto_mark_recognizes_tokens(value):
    assert is_ditto_mark(value) is True


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "AB-123",
        "Gazella sp.",
    ],
)
def test_is_ditto_mark_ignores_non_ditto_values(value):
    assert is_ditto_mark(value) is False


def test_apply_ditto_marks_copies_previous_values():
    rows = [
        {"accession_number": "KNM-ER 123", "taxon": "Gazella sp.", "locality": "Site A"},
        {"accession_number": "″", "taxon": "〃", "locality": "”"},
        {"accession_number": "KNM-ER 124", "taxon": "Hyaena sp.", "locality": "Site B"},
        {"accession_number": "11", "taxon": "!!", "locality": "(("},
    ]

    expanded = apply_ditto_marks(rows)

    assert expanded[1]["accession_number"] == "KNM-ER 123"
    assert expanded[1]["taxon"] == "Gazella sp."
    assert expanded[1]["locality"] == "Site A"
    assert expanded[3]["accession_number"] == "KNM-ER 124"
    assert expanded[3]["taxon"] == "Hyaena sp."
    assert expanded[3]["locality"] == "Site B"
