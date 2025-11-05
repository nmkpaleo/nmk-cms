import pytest

from app.cms.resources import GeologicalTimesWidget


@pytest.mark.parametrize(
    "value,expected",
    [
        ([], ""),
        (["M"], "Miocene"),
        (["M", "H"], "Miocene/Holocene"),
    ],
)
def test_geological_times_widget_render_accepts_kwargs(value, expected):
    widget = GeologicalTimesWidget()
    assert widget.render(value, export_fields=None) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("M/Pi", ["M", "Pi"]),
        ("Miocene/Pliocene", ["M", "Pi"]),
        ("Miocene/ Pi", ["M", "Pi"]),
    ],
)
def test_geological_times_widget_clean_accepts_labels_and_codes(value, expected):
    widget = GeologicalTimesWidget()
    assert widget.clean(value) == expected
