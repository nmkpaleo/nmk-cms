from __future__ import annotations

from typing import Any, Dict

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def render_field_widget(bound_field: Any, describedby: str = "", invalid: Any = False) -> str:
    """Render a bound field widget with optional accessibility attributes."""
    attrs: Dict[str, str] = {}
    if describedby:
        attrs["aria-describedby"] = describedby
    if invalid:
        attrs["aria-invalid"] = "true"
    if attrs:
        return mark_safe(bound_field.as_widget(attrs=attrs))
    return mark_safe(bound_field.as_widget())
