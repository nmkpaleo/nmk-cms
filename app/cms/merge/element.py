"""Element-specific merge helpers."""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from cms.merge.constants import MergeStrategy
from cms.models import Element


def _is_descendant(candidate: Element | None, ancestor: Element) -> bool:
    """Return ``True`` when ``candidate`` is a descendant of ``ancestor``."""

    cursor = candidate
    while cursor is not None:
        if cursor.pk == ancestor.pk:
            return True
        cursor = cursor.parent_element
    return False


def _normalise_parent_choice(value: Any) -> Element | None:
    """Coerce parent selections into :class:`Element` instances when provided."""

    if value is None or isinstance(value, Element):
        return value
    try:
        return Element.objects.get(pk=value)
    except Element.DoesNotExist as exc:  # pragma: no cover - defensive
        raise ValidationError({"parent_element": _("Selected parent element does not exist.")}) from exc


def _validate_parent_choice(*, parent: Element | None, source: Element, target: Element) -> None:
    """Guard against cycles and invalid parent selections for merges."""

    if parent is None:
        return

    if parent.pk == target.pk:
        raise ValidationError({"parent_element": _("An element cannot be its own parent.")})

    if parent.pk == source.pk:
        raise ValidationError({"parent_element": _("Cannot reparent to a source that will be removed.")})

    if _is_descendant(parent, target):
        raise ValidationError({"parent_element": _("Parent choice would create a cycle in the hierarchy.")})


def build_element_strategy_map(
    *, selected_fields: Mapping[str, Any], source: Element, target: Element
) -> MutableMapping[str, MutableMapping[str, Any]]:
    """Return a merge strategy map reflecting user selections.

    Only ``name`` and ``parent_element`` are accepted; unknown keys raise a
    :class:`ValidationError` to keep merges deterministic.
    """

    allowed_fields = {"name", "parent_element"}
    invalid = set(selected_fields) - allowed_fields
    if invalid:
        raise ValidationError(
            {
                "selected_fields": _(
                    "Unsupported fields provided for Element merge: %(fields)s"
                )
                % {"fields": ", ".join(sorted(invalid))}
            }
        )

    field_strategies: MutableMapping[str, MutableMapping[str, Any]] = {}
    for field_name, selection in selected_fields.items():
        payload: MutableMapping[str, Any] = {"strategy": MergeStrategy.FIELD_SELECTION.value}

        if field_name == "parent_element":
            if selection == "target":
                payload["selected_from"] = "target"
                resolved_parent = target.parent_element
            elif selection == "source":
                payload["selected_from"] = "source"
                resolved_parent = source.parent_element
            else:
                resolved_parent = _normalise_parent_choice(selection)
                payload["selected_from"] = "source"
                payload["value"] = resolved_parent

            _validate_parent_choice(parent=resolved_parent, source=source, target=target)
            if selection == "source" and resolved_parent is not None:
                payload["value"] = resolved_parent

        else:
            if selection in {"source", "target"}:
                payload["selected_from"] = selection
                if selection == "source":
                    payload["value"] = getattr(source, field_name)
            else:
                payload["selected_from"] = "source"
                payload["value"] = selection

        field_strategies[field_name] = payload

    return {"fields": field_strategies}

