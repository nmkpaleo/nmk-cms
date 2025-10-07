"""Core merge execution utilities."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Tuple, cast

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Model

from .constants import MergeStrategy
from .mixins import MergeMixin
from .serializers import flatten_related, serialize_instance
from . import strategies


@dataclass(frozen=True)
class MergeResult:
    """Representation of an executed merge."""

    target: MergeMixin
    resolved_values: Mapping[str, Any]
    relation_values: Mapping[str, Iterable[Any]]


def _normalize_strategy_spec(value: Any) -> Tuple[MergeStrategy, Mapping[str, Any]]:
    """Return a ``(strategy, options)`` pair from raw strategy specifications."""

    options: Mapping[str, Any] = {}
    if isinstance(value, Mapping):
        if "strategy" not in value:
            raise ValueError("Strategy mapping must include a 'strategy' key")
        strategy = MergeStrategy(value["strategy"])
        options = cast(Mapping[str, Any], {k: v for k, v in value.items() if k != "strategy"})
    else:
        strategy = MergeStrategy(value)
    return strategy, options


def _deep_merge(
    base: MutableMapping[str, Any], overrides: Mapping[str, Any] | None
) -> MutableMapping[str, Any]:
    """Recursively merge ``overrides`` into ``base`` returning a copy."""

    result: MutableMapping[str, Any] = copy.deepcopy(base)
    if not overrides:
        return result
    for key, value in overrides.items():
        if (
            key in result
            and isinstance(result[key], MutableMapping)
            and isinstance(value, Mapping)
        ):
            result[key] = _deep_merge(cast(MutableMapping[str, Any], result[key]), value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def serialize_model_state(instance: Model) -> Dict[str, Any]:
    """Return a serialised representation of the instance and its relations."""

    state: Dict[str, Any] = {
        "fields": serialize_instance(instance),
        "related": flatten_related(instance),
    }
    many_to_many: Dict[str, Iterable[Any]] = {}
    for field in instance._meta.many_to_many:  # type: ignore[attr-defined]
        manager = getattr(instance, field.name)
        many_to_many[field.name] = list(manager.values_list("pk", flat=True))
    if many_to_many:
        state["many_to_many"] = many_to_many
    return state


def _log_merge(
    *,
    source: MergeMixin,
    target: MergeMixin,
    user: Any,
    resolved_fields: Mapping[str, Any],
    resolved_relations: Mapping[str, Iterable[Any]],
    strategy_map: Mapping[str, Any],
    source_snapshot: Mapping[str, Any] | None,
    target_before: Mapping[str, Any],
    target_after: Mapping[str, Any],
) -> None:
    from cms.models import MergeLog  # Imported lazily to avoid circular imports.

    content_type = ContentType.objects.get_for_model(target, for_concrete_model=True)
    MergeLog.objects.create(
        model_label=f"{content_type.app_label}.{content_type.model}",
        source_pk=source.pk,
        target_pk=target.pk,
        resolved_values={
            "fields": resolved_fields,
            "relations": resolved_relations,
        },
        strategy_map=strategy_map,
        source_snapshot=source_snapshot,
        target_before=target_before,
        target_after=target_after,
        performed_by=user,
    )


def merge_records(
    source: MergeMixin,
    target: MergeMixin,
    strategy_map: Mapping[str, Any] | None,
    *,
    user: Any | None = None,
    dry_run: bool = False,
    archive: bool = True,
) -> MergeResult:
    """Merge ``source`` into ``target`` applying ``strategy_map`` preferences."""

    if source is target:
        raise ValueError("Source and target instances must be distinct")
    if source.__class__ is not target.__class__:
        raise TypeError("Source and target must be instances of the same model")
    if not isinstance(source, MergeMixin) or not isinstance(target, MergeMixin):
        raise TypeError("Both instances must inherit from MergeMixin")

    model_cls = source.__class__
    base_strategies: MutableMapping[str, Any] = {
        "fields": getattr(model_cls, "merge_fields", {}) or {},
        "relations": getattr(model_cls, "relation_strategies", {}) or {},
    }
    effective_strategy = _deep_merge(base_strategies, strategy_map or {})

    resolved_fields: Dict[str, Any] = {}
    resolved_relations: Dict[str, Iterable[Any]] = {}

    strategy_log: Dict[str, Any] = {}
    for category, mapping in effective_strategy.items():
        if not isinstance(mapping, Mapping):
            continue
        category_payload: Dict[str, Any] = {}
        for name, raw_value in mapping.items():
            if isinstance(raw_value, Mapping):
                strategy_name = MergeStrategy(raw_value.get("strategy")).value
                payload = {"strategy": strategy_name}
                for opt_key, opt_value in raw_value.items():
                    if opt_key == "strategy":
                        continue
                    payload[opt_key] = opt_value
            else:
                payload = {"strategy": MergeStrategy(raw_value).value}
            category_payload[name] = payload
        strategy_log[category] = category_payload

    source_snapshot = serialize_model_state(source) if archive else None
    target_before = serialize_model_state(target)

    with transaction.atomic():
        for field_name, raw_strategy in effective_strategy.get("fields", {}).items():
            strategy, options = _normalize_strategy_spec(raw_strategy)
            resolved = strategies.resolve_field(
                strategy,
                field_name=field_name,
                source=source,
                target=target,
                options=options,
            )
            if resolved is strategies.UNCHANGED:
                continue
            resolved_fields[field_name] = resolved
            setattr(target, field_name, resolved)

        update_fields = list(resolved_fields.keys())
        if update_fields and not dry_run:
            target.save(update_fields=update_fields)

        for relation_name, raw_strategy in effective_strategy.get("relations", {}).items():
            strategy, options = _normalize_strategy_spec(raw_strategy)
            resolved_relation = strategies.resolve_relation(
                strategy,
                relation_name=relation_name,
                source=source,
                target=target,
                options=options,
            )
            if resolved_relation is strategies.UNCHANGED or resolved_relation is None:
                continue
            resolved_relations[relation_name] = list(resolved_relation)
            if not dry_run:
                manager = getattr(target, relation_name)
                manager.set(resolved_relation)

        if not dry_run:
            if archive:
                target.archive_source_instance(source)
            if source.pk:
                source.delete()

        target_after = serialize_model_state(target if dry_run else model_cls.objects.get(pk=target.pk))

        if not dry_run:
            _log_merge(
                source=source,
                target=target,
                user=user,
                resolved_fields=resolved_fields,
                resolved_relations=resolved_relations,
                strategy_map=strategy_log,
                source_snapshot=source_snapshot,
                target_before=target_before,
                target_after=target_after,
            )

            target.refresh_from_db()

    return MergeResult(
        target=target,
        resolved_values=resolved_fields,
        relation_values=resolved_relations,
    )
