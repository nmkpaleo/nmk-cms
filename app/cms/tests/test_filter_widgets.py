from __future__ import annotations

import pytest

from cms import filters as cms_filters


def _extract_class_tokens(widget) -> list[str]:
    """Return all CSS class tokens applied to a widget or its subwidgets."""

    def _split_classes(class_value: str | None) -> list[str]:
        if not class_value:
            return []
        return [token for token in class_value.split() if token]

    if hasattr(widget, "widgets"):
        tokens: list[str] = []
        for subwidget in widget.widgets:
            tokens.extend(_split_classes(subwidget.attrs.get("class")))
        return tokens
    return _split_classes(widget.attrs.get("class"))


@pytest.mark.django_db
@pytest.mark.parametrize(
    "filter_cls",
    [
        cms_filters.AccessionFilter,
        cms_filters.PreparationFilter,
        cms_filters.LocalityFilter,
        cms_filters.PlaceFilter,
        cms_filters.ReferenceFilter,
        cms_filters.FieldSlipFilter,
        cms_filters.DrawerRegisterFilter,
        cms_filters.StorageFilter,
    ],
)
def test_filter_widgets_expose_w3_classes(filter_cls):
    model = filter_cls.Meta.model
    filterset = filter_cls(data={}, queryset=model.objects.none())
    for field in filterset.form.fields.values():
        tokens = _extract_class_tokens(field.widget)
        assert any(token.startswith("w3-") for token in tokens), (
            f"Expected at least one W3.CSS class on field '{field.label}'"
        )
