import pytest

from app.cms.resources import GeologicalTimesWidget


@pytest.mark.parametrize(
    "value,expected",
    [
        ([], ""),
        (["M"], "M"),
        (["M", "H"], "M/H"),
    ],
)
def test_geological_times_widget_render_accepts_kwargs(value, expected):
    widget = GeologicalTimesWidget()
    assert widget.render(value, export_fields=None) == expected
