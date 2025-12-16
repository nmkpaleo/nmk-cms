"""Service helpers wrapping merge execution for specific models."""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from cms.merge.constants import MergeStrategy
from cms.merge.engine import MergeResult, merge_records
from cms.merge.element import build_element_strategy_map
from cms.models import AccessionReference, Element


def build_accession_reference_strategy_map(
    *,
    selected_fields: Mapping[str, Any],
    source: AccessionReference,
    target: AccessionReference,
) -> MutableMapping[str, MutableMapping[str, Any]]:
    """Return a FIELD_SELECTION strategy map for accession reference merges."""

    allowed_fields = {"reference", "page"}
    invalid = set(selected_fields) - allowed_fields
    if invalid:
        raise ValidationError(
            {
                "selected_fields": _(
                    "Unsupported fields provided for AccessionReference merge: %(fields)s"
                )
                % {"fields": ", ".join(sorted(invalid))}
            }
        )

    field_strategies: MutableMapping[str, MutableMapping[str, Any]] = {}
    for field_name, selection in selected_fields.items():
        payload: MutableMapping[str, Any] = {"strategy": MergeStrategy.FIELD_SELECTION.value}

        if selection in {"source", "target"}:
            payload["selected_from"] = selection
            if selection == "source":
                payload["value"] = getattr(source, field_name)
        else:
            payload["selected_from"] = "source"
            payload["value"] = selection

        field_strategies[field_name] = payload

    if not field_strategies:
        return {"fields": {"reference": {"strategy": MergeStrategy.FIELD_SELECTION.value, "selected_from": "target"}}}

    return {"fields": field_strategies}


def merge_elements(
    *,
    source: Element,
    target: Element,
    selected_fields: Mapping[str, Any] | None = None,
    user: Any | None = None,
    dry_run: bool = False,
) -> MergeResult:
    """Merge ``source`` Element into ``target`` using FIELD_SELECTION semantics.

    ``selected_fields`` should map field names (``name`` or ``parent_element``)
    to one of:

    - ``"source"`` or ``"target"`` to keep the corresponding record's value.
    - An :class:`Element`, primary key, or ``None`` for explicit parent choices.
    - A raw value for ``name``.

    Raises :class:`ValidationError` when inputs would lead to invalid hierarchy
    relationships or unsupported fields. All writes are wrapped in the core
    merge transaction and emit :class:`cms.models.MergeLog` entries.
    """

    if source.pk is None or target.pk is None:
        raise ValidationError({"source": "Merge candidates must be saved records."})
    if source.pk == target.pk:
        raise ValidationError({"source": "Source and target must differ."})

    strategy_map = (
        build_element_strategy_map(selected_fields=selected_fields or {}, source=source, target=target)
        if selected_fields
        else None
    )

    return merge_records(
        source=source,
        target=target,
        strategy_map=strategy_map,
        user=user,
        dry_run=dry_run,
    )


def merge_accession_references(
    *,
    source: AccessionReference,
    target: AccessionReference,
    strategy_map: Mapping[str, Any] | None = None,
    selected_fields: Mapping[str, Any] | None = None,
    user: Any | None = None,
    dry_run: bool = False,
) -> MergeResult:
    """Merge ``source`` accession reference into ``target``.

    Supports ``strategy_map`` values produced by
    :class:`cms.forms.AccessionReferenceFieldSelectionForm` or raw
    ``selected_fields`` maps used to build a FIELD_SELECTION payload for the
    ``reference`` and ``page`` fields.
    """

    if source.pk is None or target.pk is None:
        raise ValidationError({"source": _("Merge candidates must be saved records.")})
    if source.pk == target.pk:
        raise ValidationError({"source": _("Source and target must differ.")})
    if source.accession_id != target.accession_id:
        raise ValidationError(
            {"accession": _("Accession references must belong to the same accession.")}
        )

    field_selection_map = strategy_map
    if field_selection_map is None:
        field_selection_map = build_accession_reference_strategy_map(
            selected_fields=selected_fields or {"reference": "target", "page": "target"},
            source=source,
            target=target,
        )

    return merge_records(
        source=source,
        target=target,
        strategy_map=field_selection_map,
        user=user,
        dry_run=dry_run,
    )

