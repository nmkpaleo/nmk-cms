from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from django.db import transaction
from django.db.models import Model
from django.utils.translation import gettext_lazy as _

from cms.merge.constants import MergeStrategy
from cms.merge.engine import MergeResult, merge_records
from cms.merge.mixins import MergeMixin
from cms.merge.strategies import _normalize_strategy_spec


@dataclass(frozen=True)
class FieldSelection:
    """Representation of a user-provided field selection."""

    field_name: str
    selected_key: str


class FieldSelectionMergeService:
    """Apply FIELD_SELECTION merge strategies with validation and transactions."""

    def __init__(self, model: type[MergeMixin]):
        if not issubclass(model, MergeMixin):
            raise TypeError(_("Merge service requires a MergeMixin model."))
        self.model = model

    def merge(
        self,
        *,
        target: MergeMixin,
        sources: Iterable[MergeMixin],
        selections: Mapping[str, str],
        user: Any | None = None,
        archive: bool = True,
    ) -> Sequence[MergeResult]:
        """Merge ``sources`` into ``target`` applying field selections.

        ``selections`` maps field names to candidate identifiers (primary keys as
        strings). Only fields configured with the ``FIELD_SELECTION`` strategy
        are permitted.
        """

        validated_target = self._validate_target(target)
        validated_sources = self._validate_sources(sources, validated_target)
        selection_specs = self._validate_selections(selections, validated_target, validated_sources)
        strategy_map = self._build_strategy_map(selection_specs, validated_target, validated_sources)

        merge_results: list[MergeResult] = []
        current_target = validated_target

        with transaction.atomic():
            for source in validated_sources:
                result = merge_records(
                    source=source,
                    target=current_target,
                    strategy_map=strategy_map,
                    user=user,
                    archive=archive,
                )
                merge_results.append(result)
                current_target = result.target

        return tuple(merge_results)

    def _validate_target(self, target: MergeMixin) -> MergeMixin:
        if not isinstance(target, self.model):
            raise TypeError(_("Target must be an instance of the merge model."))
        if getattr(target, "pk", None) is None:
            raise ValueError(_("Target instance must have a primary key."))
        return target

    def _validate_sources(
        self, sources: Iterable[MergeMixin], target: MergeMixin
    ) -> Sequence[MergeMixin]:
        validated: list[MergeMixin] = []
        for source in sources:
            if not isinstance(source, self.model):
                raise TypeError(_("All merge sources must match the merge model."))
            if getattr(source, "pk", None) is None:
                raise ValueError(_("Merge sources must have a primary key."))
            if source.pk == target.pk:
                raise ValueError(_("Source and target must be different records."))
            validated.append(source)

        if not validated:
            raise ValueError(_("At least one source record is required for merging."))

        return tuple(validated)

    def _validate_selections(
        self,
        selections: Mapping[str, str],
        target: MergeMixin,
        sources: Sequence[MergeMixin],
    ) -> Sequence[FieldSelection]:
        allowed_fields = self._field_selection_enabled_fields()
        candidate_keys = {**{str(target.pk): target}, **{str(src.pk): src for src in sources}}
        validated: list[FieldSelection] = []

        for field_name, candidate_key in selections.items():
            if field_name not in allowed_fields:
                raise ValueError(
                    _("Field '%(field)s' does not support field selection.")
                    % {"field": field_name}
                )
            if candidate_key not in candidate_keys:
                raise ValueError(
                    _("Selection for '%(field)s' references an unknown candidate.")
                    % {"field": field_name}
                )
            validated.append(FieldSelection(field_name=field_name, selected_key=str(candidate_key)))

        return tuple(validated)

    def _field_selection_enabled_fields(self) -> set[str]:
        enabled: set[str] = set()
        for field_name, raw_strategy in (getattr(self.model, "merge_fields", {}) or {}).items():
            strategy, _ = _normalize_strategy_spec(raw_strategy)
            if strategy is MergeStrategy.FIELD_SELECTION:
                enabled.add(field_name)
        return enabled

    def _build_strategy_map(
        self,
        selections: Sequence[FieldSelection],
        target: MergeMixin,
        sources: Sequence[MergeMixin],
    ) -> MutableMapping[str, Any]:
        strategy_map: MutableMapping[str, Any] = {"fields": {}}
        candidate_lookup: dict[str, Model] = {str(target.pk): target}
        candidate_lookup.update({str(source.pk): source for source in sources})

        for selection in selections:
            candidate = candidate_lookup[selection.selected_key]
            if candidate.pk == target.pk:
                payload: Mapping[str, Any] = {
                    "strategy": MergeStrategy.FIELD_SELECTION.value,
                    "selected_from": "target",
                }
            else:
                field = self.model._meta.get_field(selection.field_name)  # type: ignore[attr-defined]
                payload = {
                    "strategy": MergeStrategy.FIELD_SELECTION.value,
                    "selected_from": "source",
                    "value": field.value_from_object(candidate),
                }
            strategy_map["fields"][selection.field_name] = payload

        return strategy_map


def merge_with_field_selection(
    *,
    model: type[MergeMixin],
    target: MergeMixin,
    sources: Iterable[MergeMixin],
    selections: Mapping[str, str],
    user: Any | None = None,
    archive: bool = True,
) -> Sequence[MergeResult]:
    """Functional wrapper around :class:`FieldSelectionMergeService`."""

    service = FieldSelectionMergeService(model)
    return service.merge(
        target=target,
        sources=sources,
        selections=selections,
        user=user,
        archive=archive,
    )
