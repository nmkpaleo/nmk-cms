"""Service helpers wrapping merge execution for specific models."""
from __future__ import annotations

from typing import Any, Mapping

from django.core.exceptions import ValidationError

from cms.merge.engine import MergeResult, merge_records
from cms.merge.element import build_element_strategy_map
from cms.models import Element


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

