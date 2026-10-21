"""Service helpers wrapping merge execution for specific models."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, MutableMapping

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from cms.forms import AccessionReferenceFieldSelectionForm, FieldSelectionCandidate
from cms.merge.constants import MergeStrategy
from cms.merge.engine import MergeResult, merge_records
from cms.merge.element import build_element_strategy_map
from cms.models import AccessionReference, Element


logger = logging.getLogger(__name__)


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


@dataclass
class BulkMergeReport:
    """Outcome of a bulk accession reference merge."""

    groups_found: int = 0
    groups_merged: int = 0
    rows_merged: int = 0
    failures: list[str] = field(default_factory=list)


def combine_pages(pages: Iterable[str | None]) -> str:
    """Return unique, ascending, comma-separated page values."""

    values = {
        part.strip()
        for page in pages
        if page
        for part in page.split(",")
        if part.strip()
    }
    if all(value.isdigit() for value in values):
        ordered = sorted(values, key=int)
    else:
        ordered = sorted(
            values,
            key=lambda v: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", v)],
        )
    return ", ".join(ordered)


def find_duplicate_accession_reference_groups() -> list[list[AccessionReference]]:
    """Group accession references sharing accession and reference (lowest pk first)."""

    duplicate_pairs = (
        AccessionReference.objects.values("accession_id", "reference_id")
        .annotate(total=models.Count("pk"))
        .filter(total__gt=1)
    )
    groups: list[list[AccessionReference]] = []
    for pair in duplicate_pairs:
        groups.append(
            list(
                AccessionReference.objects.filter(
                    accession_id=pair["accession_id"], reference_id=pair["reference_id"]
                ).order_by("pk")
            )
        )
    return groups


def bulk_merge_duplicate_accession_references(
    *, user: Any | None = None
) -> BulkMergeReport:
    """Merge every duplicate accession/reference group into its lowest-pk row.

    Pages from all rows are combined. Each group runs in its own transaction so
    a failure does not block other groups.
    """

    page_max_length = AccessionReference._meta.get_field("page").max_length
    groups = find_duplicate_accession_reference_groups()
    report = BulkMergeReport(groups_found=len(groups))

    for rows in groups:
        target, sources = rows[0], rows[1:]
        label = f"{target.accession} / {target.reference}"
        combined = combine_pages(row.page for row in rows)
        if len(combined) > page_max_length:
            report.failures.append(
                _("%(label)s: combined page '%(page)s' exceeds %(max)d characters.")
                % {"label": label, "page": combined, "max": page_max_length}
            )
            continue
        try:
            with transaction.atomic():
                for source in sources:
                    merge_accession_references(
                        source=source,
                        target=target,
                        selected_fields={"reference": "target", "page": combined or None},
                        user=user,
                    )
                    target.refresh_from_db()
        except Exception as exc:  # noqa: BLE001 - reported to the admin user
            logger.exception("Bulk accession reference merge failed for %s", label)
            report.failures.append(f"{label}: {exc}")
            continue
        report.groups_merged += 1
        report.rows_merged += len(sources)

    return report


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

