"""Service helpers wrapping merge execution for specific models."""
from __future__ import annotations

from typing import Any, Iterable, Mapping, MutableMapping

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from cms.forms import (
    AccessionElementFieldSelectionForm,
    AccessionReferenceFieldSelectionForm,
    FieldSelectionCandidate,
)
from cms.merge.constants import MergeStrategy
from cms.merge.engine import MergeResult, merge_records
from cms.merge.element import build_element_strategy_map
from cms.models import AccessionReference, Element, NatureOfSpecimen


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


def _ensure_same_accession(
    candidates: Iterable[AccessionReference],
) -> None:
    accession_ids = {candidate.accession_id for candidate in candidates}
    if len(accession_ids) > 1:
        raise ValidationError(
            {"accession": _("Accession references must belong to the same accession.")}
        )


def build_accession_reference_field_selection_form(
    *,
    candidate_ids: Iterable[str | int],
    target_id: str | int | None = None,
    data: dict[str, object] | None = None,
    initial: dict[str, object] | None = None,
) -> AccessionReferenceFieldSelectionForm:
    """Return a FIELD_SELECTION form for accession reference candidates.

    Ensures candidates belong to the same accession and annotates the target
    candidate so FIELD_SELECTION defaults favour the chosen target.
    """

    ordered_ids = []
    for raw_id in candidate_ids:
        value = str(raw_id)
        if value and value not in ordered_ids:
            ordered_ids.append(value)

    if len(ordered_ids) < 2:
        raise ValidationError({"selected_ids": _("Select at least two records to merge.")})

    candidates = list(
        AccessionReference.objects.filter(pk__in=ordered_ids).select_related("reference")
    )
    candidate_map = {str(candidate.pk): candidate for candidate in candidates}
    resolved_candidates: list[FieldSelectionCandidate] = []

    if target_id is None:
        target_id = ordered_ids[0]

    try:
        _ensure_same_accession(candidate_map.values())
    except ValidationError:
        raise

    for pk in ordered_ids:
        candidate = candidate_map.get(pk)
        if candidate is None:
            continue
        resolved_candidates.append(
            FieldSelectionCandidate.from_instance(
                candidate, role="target" if str(pk) == str(target_id) else "source"
            )
        )

    if len(resolved_candidates) < 2:
        raise ValidationError(
            {"selected_ids": _("Select at least two existing records to merge.")}
        )

    return AccessionReferenceFieldSelectionForm(
        candidates=resolved_candidates,
        data=data,
        initial=initial,
    )


def merge_accession_reference_candidates(
    *,
    target: AccessionReference,
    sources: Iterable[AccessionReference],
    form: AccessionReferenceFieldSelectionForm,
    user: Any | None = None,
    dry_run: bool = False,
) -> list[MergeResult]:
    """Merge ``sources`` into ``target`` using FIELD_SELECTION strategies."""

    if target.pk is None:
        raise ValidationError({"target": _("Merge candidates must be saved records.")})

    unique_sources: list[AccessionReference] = []
    seen: set[str] = set()
    for source in sources:
        if source.pk is None:
            raise ValidationError({"source": _("Merge candidates must be saved records.")})
        if str(source.pk) in seen or source.pk == target.pk:
            continue
        seen.add(str(source.pk))
        unique_sources.append(source)

    if not unique_sources:
        raise ValidationError({"selected_ids": _("Select at least one source to merge.")})

    _ensure_same_accession([target, *unique_sources])

    strategy_map = form.build_strategy_map()
    for field in form.merge_fields:
        payload = strategy_map.get("fields", {}).get(field.name)
        if not payload:
            continue
        if isinstance(field, models.ForeignKey):
            value = payload.get("value")
            if value not in (None, "") and not isinstance(value, models.Model):
                try:
                    payload["value"] = field.remote_field.model._default_manager.get(pk=value)
                except field.remote_field.model.DoesNotExist:
                    raise ValidationError(
                        {field.name: _("Selected reference no longer exists.")}
                    )
    results: list[MergeResult] = []
    current_target = target

    for source in unique_sources:
        merge_result = merge_accession_references(
            source=source,
            target=current_target,
            strategy_map=strategy_map,
            user=user,
            dry_run=dry_run,
        )
        results.append(merge_result)
        current_target = merge_result.target

    return results


class NatureOfSpecimenMergeResult(MergeResult):
    """Lightweight result wrapper for NatureOfSpecimen merges."""

    def __init__(self, target: NatureOfSpecimen, resolved_values: Mapping[str, Any], relation_actions=None):
        super().__init__(target=target, resolved_values=resolved_values, relation_actions=relation_actions or {})


def _ensure_same_accession_row(candidates: Iterable[NatureOfSpecimen]) -> None:
    accession_row_ids = {candidate.accession_row_id for candidate in candidates}
    if len(accession_row_ids) > 1:
        raise ValidationError({"accession_row": _("Elements must belong to the same accession row.")})


def build_accession_element_field_selection_form(
    *,
    candidate_ids: Iterable[str | int],
    target_id: str | int | None = None,
    data: dict[str, object] | None = None,
    initial: dict[str, object] | None = None,
) -> AccessionElementFieldSelectionForm:
    """Return a FIELD_SELECTION form for NatureOfSpecimen candidates."""

    ordered_ids: list[str] = []
    for raw_id in candidate_ids:
        value = str(raw_id)
        if value and value not in ordered_ids:
            ordered_ids.append(value)

    if len(ordered_ids) < 2:
        raise ValidationError({"selected_ids": _("Select at least two records to merge.")})

    candidates = list(
        NatureOfSpecimen.objects.filter(pk__in=ordered_ids).select_related("element", "accession_row")
    )
    candidate_map = {str(candidate.pk): candidate for candidate in candidates}
    resolved_candidates: list[FieldSelectionCandidate] = []

    if target_id is None:
        target_id = ordered_ids[0]

    _ensure_same_accession_row(candidate_map.values())

    for pk in ordered_ids:
        candidate = candidate_map.get(pk)
        if candidate is None:
            continue
        resolved_candidates.append(
            FieldSelectionCandidate.from_instance(
                candidate, role="target" if str(pk) == str(target_id) else "source"
            )
        )

    if len(resolved_candidates) < 2:
        raise ValidationError(
            {"selected_ids": _("Select at least two existing records to merge.")}
        )

    return AccessionElementFieldSelectionForm(
        candidates=resolved_candidates,
        data=data,
        initial=initial,
    )


def merge_nature_of_specimen(
    *,
    source: NatureOfSpecimen,
    target: NatureOfSpecimen,
    selected_fields: Mapping[str, Any] | None = None,
    user: Any | None = None,
    dry_run: bool = False,
) -> NatureOfSpecimenMergeResult:
    """Merge ``source`` NatureOfSpecimen into ``target`` with field selections."""

    if source.pk is None or target.pk is None:
        raise ValidationError({"source": _("Merge candidates must be saved records.")})
    if source.pk == target.pk:
        raise ValidationError({"source": _("Source and target must differ.")})
    if source.accession_row_id != target.accession_row_id:
        raise ValidationError({"accession_row": _("Elements must belong to the same accession row.")})

    allowed_fields = {
        "element",
        "side",
        "condition",
        "verbatim_element",
        "portion",
        "fragments",
    }
    selected_fields = selected_fields or {}
    invalid = set(selected_fields) - allowed_fields
    if invalid:
        raise ValidationError({"selected_fields": _("Unsupported fields: %(fields)s") % {"fields": ", ".join(sorted(invalid))}})

    resolved_values: dict[str, Any] = {}
    for field_name, selection in selected_fields.items():
        if selection == "target":
            continue
        if selection == "source":
            resolved_values[field_name] = getattr(source, field_name)
        else:
            resolved_values[field_name] = selection

    element_value = resolved_values.get("element")
    if element_value not in (None, "") and not isinstance(element_value, Element):
        try:
            resolved_values["element"] = Element.objects.get(pk=element_value)
        except Element.DoesNotExist:
            raise ValidationError({"element": _("Selected element no longer exists.")})

    updated_fields: dict[str, Any] = {}
    for field_name, value in resolved_values.items():
        setattr(target, field_name, value)
        updated_fields[field_name] = value

    deleted_source_ids: list[int] = []
    if not dry_run:
        target.save()
        deleted_source_ids.append(source.pk)
        source.delete()

    return NatureOfSpecimenMergeResult(
        target=target,
        resolved_values=updated_fields,
        relation_actions={"deleted_source_ids": deleted_source_ids},
    )


def merge_nature_of_specimen_candidates(
    *,
    target: NatureOfSpecimen,
    sources: Iterable[NatureOfSpecimen],
    form: AccessionElementFieldSelectionForm,
    user: Any | None = None,
    dry_run: bool = False,
) -> list[NatureOfSpecimenMergeResult]:
    """Merge ``sources`` into ``target`` using field selections."""

    if target.pk is None:
        raise ValidationError({"target": _("Merge candidates must be saved records.")})

    unique_sources: list[NatureOfSpecimen] = []
    seen: set[str] = set()
    for source in sources:
        if source.pk is None:
            raise ValidationError({"source": _("Merge candidates must be saved records.")})
        if str(source.pk) in seen or source.pk == target.pk:
            continue
        seen.add(str(source.pk))
        unique_sources.append(source)

    if not unique_sources:
        raise ValidationError({"selected_ids": _("Select at least one source to merge.")})

    _ensure_same_accession_row([target, *unique_sources])

    selected_fields = form.build_selected_fields()
    results: list[NatureOfSpecimenMergeResult] = []
    current_target = target

    for source in unique_sources:
        merge_result = merge_nature_of_specimen(
            source=source,
            target=current_target,
            selected_fields=selected_fields,
            user=user,
            dry_run=dry_run,
        )
        results.append(merge_result)
        current_target = merge_result.target

    return results
