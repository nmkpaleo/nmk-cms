"""Utilities to capture and serialise the state of Django model instances."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping

from django.forms.models import model_to_dict


def serialize_instance(
    instance,
    *,
    fields: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
) -> Dict[str, Any]:
    """Return a dictionary representing the model's current state."""

    return model_to_dict(instance, fields=fields, exclude=exclude)


def flatten_related(instance) -> Mapping[str, Any]:
    """Return a mapping of related field names to their primary keys."""

    related_state: Dict[str, Any] = {}
    for field in instance._meta.related_objects:  # type: ignore[attr-defined]
        accessor = getattr(instance, field.get_accessor_name())
        if field.one_to_many or field.many_to_many:
            related_state[field.name] = list(accessor.values_list("pk", flat=True))
        else:
            related_state[field.name] = getattr(accessor, "pk", None)
    return related_state
