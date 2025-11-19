"""Custom form rendering helpers used in shared templates."""
from __future__ import annotations

from typing import Any, Dict

from django import template

register = template.Library()


def _merge_classes(existing: str | None, new: str | None) -> str | None:
    classes = []
    if existing:
        classes.append(existing)
    if new:
        classes.append(new)
    if not classes:
        return None
    # Collapse whitespace and deduplicate while preserving order.
    seen = set()
    ordered = []
    for chunk in " ".join(classes).split():
        if chunk not in seen:
            seen.add(chunk)
            ordered.append(chunk)
    return " ".join(ordered)


@register.simple_tag
def render_form_field(field, css_class: str | None = None, placeholder: str | None = None, **attrs: Any) -> str:
    """Render ``field`` with merged CSS classes and optional placeholder."""

    widget_attrs: Dict[str, Any] = {}
    if hasattr(field.field.widget, "attrs"):
        widget_attrs.update(field.field.widget.attrs)

    merged_class = _merge_classes(widget_attrs.get("class"), css_class)
    if merged_class:
        widget_attrs["class"] = merged_class

    if placeholder is not None:
        widget_attrs["placeholder"] = placeholder

    widget_attrs.update(attrs)
    return field.as_widget(attrs=widget_attrs)
