import pytest

from cms.utils import coerce_stripped, normalise_yes_no


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
