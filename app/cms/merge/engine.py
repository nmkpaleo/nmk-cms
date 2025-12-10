"""Core merge execution utilities."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping, Optional, cast

from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.db.models import Model
from django.db.models.fields.related import (
    ForeignObjectRel,
    ManyToManyField,
    ManyToManyRel,
    OneToOneRel,
)

from .constants import MergeStrategy
from .mixins import MergeMixin
from .serializers import flatten_related, serialize_instance
from . import strategies


@dataclass(frozen=True)
class MergeResult:
    """Representation of an executed merge."""

    target: MergeMixin
    resolved_values: Mapping[str, strategies.StrategyResolution]
    relation_actions: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True)
class RelationDirective:
    """Normalised representation of relation handling instructions."""

    action: str
    options: Mapping[str, Any]
    callback: Optional[Callable[..., Mapping[str, Any] | None]] = None


RELATION_ACTION_REASSIGN = "reassign"
RELATION_ACTION_MERGE = "merge"
RELATION_ACTION_SKIP = "skip"
RELATION_ACTION_STRATEGY = "strategy"
RELATION_ACTION_CUSTOM = "custom"


def _default_relation_action(field: Any) -> str:
    """Return the default action that should be applied to ``field``."""

    if isinstance(field, (ManyToManyRel, ManyToManyField)):
        return RELATION_ACTION_MERGE
    if isinstance(field, (ForeignObjectRel, OneToOneRel)):
        return RELATION_ACTION_REASSIGN
    return RELATION_ACTION_SKIP


def _serialise_callable(value: Callable[..., Any] | None) -> str | None:
    """Return a dotted path representation for ``value`` when available."""

    if not callable(value):
        return None
    module = getattr(value, "__module__", None)
    qualname = getattr(value, "__qualname__", getattr(value, "__name__", None))
    if module and qualname:
        return f"{module}.{qualname}"
    if qualname:
        return qualname
    return repr(value)


def _normalise_relation_spec(field: Any, raw_value: Any) -> RelationDirective:
    """Normalise ``raw_value`` into a :class:`RelationDirective`."""

    action = None
    options: Mapping[str, Any] = {}
    callback: Optional[Callable[..., Mapping[str, Any] | None]] = None

    if callable(raw_value):
        action = RELATION_ACTION_CUSTOM
        callback = cast(Callable[..., Mapping[str, Any] | None], raw_value)
    elif isinstance(raw_value, Mapping):
        mapping = cast(Mapping[str, Any], raw_value)
        if "callback" in mapping and callable(mapping["callback"]):
            callback = cast(Callable[..., Mapping[str, Any] | None], mapping["callback"])
            action = mapping.get("action", RELATION_ACTION_CUSTOM)
        elif "callable" in mapping and callable(mapping["callable"]):
            callback = cast(Callable[..., Mapping[str, Any] | None], mapping["callable"])
            action = mapping.get("action", RELATION_ACTION_CUSTOM)
        else:
            strategy_value = mapping.get("strategy")
            if isinstance(strategy_value, MergeStrategy):
                options = {
                    "strategy": strategy_value,
                    **{
                        k: v
                        for k, v in mapping.items()
                        if k not in {"strategy", "callback", "callable"}
                    },
                }
                action = RELATION_ACTION_STRATEGY
            elif isinstance(strategy_value, str) and strategy_value in MergeStrategy._value2member_map_:
                options = {
                    "strategy": MergeStrategy(strategy_value),
                    **{
                        k: v
                        for k, v in mapping.items()
                        if k not in {"strategy", "callback", "callable"}
                    },
                }
                action = RELATION_ACTION_STRATEGY
            else:
                action = cast(str, mapping.get("action"))
                options = {
                    k: v
                    for k, v in mapping.items()
                    if k not in {"action", "callback", "callable"}
                }
    elif isinstance(raw_value, MergeStrategy):
        options = {"strategy": raw_value}
        action = RELATION_ACTION_STRATEGY
    elif isinstance(raw_value, str):
        if raw_value in MergeStrategy._value2member_map_:
            options = {"strategy": MergeStrategy(raw_value)}
            action = RELATION_ACTION_STRATEGY
        else:
            action = raw_value

    if not action:
        action = _default_relation_action(field)

    if action == RELATION_ACTION_CUSTOM and callback is None:
        raise ValueError("Custom relation directives require a callable callback")

    return RelationDirective(action=action, options=options, callback=callback)


def _serialise_value(value: Any) -> Any:
    """Return a JSON-safe representation of ``value`` suitable for logging."""

    if isinstance(value, Model):
        return getattr(value, "pk", str(value))
    if isinstance(value, Mapping):
        return {k: _serialise_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialise_value(item) for item in value]
    if hasattr(value, "pk"):
        return getattr(value, "pk")

    try:
        return json.loads(json.dumps(value, cls=DjangoJSONEncoder))
    except TypeError:
        return str(value)


def _unique_constraint_combinations(
    model: type[Model], related_field_name: str
) -> list[tuple[str, ...]]:
    """Return unique constraint field combinations including ``related_field_name``."""

    opts = model._meta
    combinations: list[tuple[str, ...]] = []

    unique_together = getattr(opts, "unique_together", []) or []
    for fields in unique_together:
        if not fields:
            continue
        if related_field_name in fields:
            combinations.append(tuple(fields))

    for constraint in getattr(opts, "constraints", []):
        if not isinstance(constraint, models.UniqueConstraint):
            continue
        constraint_fields = getattr(constraint, "fields", None) or []
        if related_field_name in constraint_fields:
            combinations.append(tuple(constraint_fields))

    return combinations


def _build_unique_lookup(
    *,
    combination: tuple[str, ...],
    related_field: models.Field,
    related_object: Model,
    target: MergeMixin,
) -> Dict[str, Any]:
    """Return a lookup dict for ``combination`` reflecting reassignment to ``target``."""

    lookup: Dict[str, Any] = {}
    opts = related_object._meta

    for field_name in combination:
        try:
            model_field = opts.get_field(field_name)
        except Exception:
            # If the field definition cannot be resolved we skip the lookup,
            # allowing the caller to ignore empty dictionaries.
            return {}

        if isinstance(model_field, models.ForeignKey):
            attname = model_field.attname
            if field_name == related_field.name:
                lookup[attname] = target.pk
            else:
                lookup[attname] = getattr(related_object, attname)
        else:
            if field_name == related_field.name:
                lookup[field_name] = getattr(target, field_name, target.pk)
            else:
                lookup[field_name] = getattr(related_object, field_name)

    return lookup


def _reassign_related_objects(
    *,
    field: ForeignObjectRel | OneToOneRel,
    relation_name: str,
    source: MergeMixin,
    target: MergeMixin,
    dry_run: bool,
    options: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Reassign FK/one-to-one relations from ``source`` to ``target``."""

    related_field = field.field
    attname = related_field.attname
    log_payload: Dict[str, Any] = {"action": RELATION_ACTION_REASSIGN}

    if isinstance(field, OneToOneRel):
        accessor = field.get_accessor_name()
        try:
            related_obj = getattr(source, accessor)
        except field.related_model.DoesNotExist:  # type: ignore[attr-defined]
            log_payload["updated"] = 0
            return log_payload

        target_has = True
        try:
            getattr(target, accessor)
        except field.related_model.DoesNotExist:  # type: ignore[attr-defined]
            target_has = False

        if target_has:
            log_payload["skipped"] = 1
            log_payload["reason"] = "target_has_relation"
            return log_payload

        if not dry_run:
            setattr(related_obj, field.field.name, target)
            related_obj.save(update_fields=[field.field.name])

        log_payload["updated"] = 1
        return log_payload

    manager = getattr(source, relation_name)
    queryset = manager.select_for_update()
    total = queryset.count()
    if not total:
        log_payload["updated"] = 0
        return log_payload

    deduplicate = bool(
        options.get("deduplicate")
        or options.get("skip_conflicts")
        or options.get("deduplicate_conflicts")
    )
    delete_conflicts = bool(options.get("delete_conflicts", True))

    update_ids: list[Any]
    conflict_ids: list[Any] = []

    if deduplicate:
        related_model = queryset.model
        combinations = list(
            _unique_constraint_combinations(related_model, related_field.name)
        )

        extra_combinations = options.get("unique_fields")
        if isinstance(extra_combinations, (list, tuple)):
            for combo in extra_combinations:
                if not isinstance(combo, (list, tuple)):
                    continue
                if related_field.name not in combo:
                    continue
                combinations.append(tuple(combo))

        related_objects = list(queryset)
        update_ids = []

        if combinations:
            for related_object in related_objects:
                has_conflict = False
                for combination in combinations:
                    lookup = _build_unique_lookup(
                        combination=combination,
                        related_field=related_field,
                        related_object=related_object,
                        target=target,
                    )
                    if not lookup:
                        continue
                    existing_qs = (
                        related_model._default_manager.select_for_update()
                        .filter(**lookup)
                        .exclude(pk=related_object.pk)
                    )
                    if existing_qs.exists():
                        has_conflict = True
                        break
                if has_conflict:
                    conflict_ids.append(related_object.pk)
                else:
                    update_ids.append(related_object.pk)
        else:
            update_ids = [obj.pk for obj in related_objects if obj.pk is not None]
    else:
        update_ids = list(queryset.values_list("pk", flat=True))

    updated_count = len(update_ids)

    if not dry_run and conflict_ids and delete_conflicts:
        queryset.model._default_manager.filter(pk__in=conflict_ids).delete()
        log_payload["deleted"] = len(conflict_ids)
    elif dry_run and conflict_ids and delete_conflicts:
        log_payload["would_delete"] = len(conflict_ids)

    if conflict_ids:
        log_payload["skipped"] = len(conflict_ids)

    if not dry_run and update_ids:
        update_kwargs = {attname: target.pk}
        queryset.model._default_manager.filter(pk__in=update_ids).update(**update_kwargs)

    log_payload["updated"] = updated_count
    return log_payload


def _merge_many_to_many(
    *,
    field: ManyToManyField | ManyToManyRel,
    relation_name: str,
    source: MergeMixin,
    target: MergeMixin,
    dry_run: bool,
    options: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Merge many-to-many relations by unifying membership sets."""

    allow = options.get("allow") or options.get("allowed")
    allow_set = set(allow or []) if allow else None

    source_manager = getattr(source, relation_name)
    target_manager = getattr(target, relation_name)

    source_ids = set(source_manager.values_list("pk", flat=True))
    target_ids = set(target_manager.values_list("pk", flat=True))

    if allow_set is not None:
        source_ids &= allow_set

    if not source_ids:
        return {"action": RELATION_ACTION_MERGE, "added": 0, "skipped": 0}

    missing_ids = sorted(source_ids - target_ids)
    skipped = len(source_ids & target_ids)
    added = 0

    if not dry_run and missing_ids:
        through_model = source_manager.through
        if getattr(through_model._meta, "auto_created", False):
            target_manager.add(*missing_ids)
            added = len(missing_ids)
        else:
            source_field_name = source_manager.source_field_name
            target_field_name = source_manager.target_field_name
            through_qs = (
                through_model._default_manager.select_for_update()
                .filter(**{f"{source_field_name}_id": source.pk})
                .filter(**{f"{target_field_name}_id__in": missing_ids})
            )
            for link in through_qs:
                remote_id = getattr(link, f"{target_field_name}_id")
                exists = through_model._default_manager.filter(
                    **{
                        f"{source_field_name}_id": target.pk,
                        f"{target_field_name}_id": remote_id,
                    }
                ).exists()
                if exists:
                    skipped += 1
                    continue
                setattr(link, f"{source_field_name}_id", target.pk)
                link.save(update_fields=[f"{source_field_name}_id"])
                added += 1
    elif not dry_run:
        added = len(missing_ids)

    return {
        "action": RELATION_ACTION_MERGE,
        "added": added if not dry_run else len(missing_ids),
        "skipped": skipped,
    }


def _apply_relation_directive(
    *,
    directive: RelationDirective,
    field: Any,
    relation_name: str,
    source: MergeMixin,
    target: MergeMixin,
    dry_run: bool,
) -> Mapping[str, Any] | None:
    """Execute ``directive`` for ``relation_name`` returning a log payload."""

    if directive.action == RELATION_ACTION_SKIP:
        return {"action": RELATION_ACTION_SKIP}

    if directive.action == RELATION_ACTION_STRATEGY:
        strategy = directive.options.get("strategy")
        if not isinstance(field, (ManyToManyRel, ManyToManyField)):
            raise TypeError(
                "Strategy based relation handling is only supported for many-to-many relations"
            )
        if not isinstance(strategy, MergeStrategy):
            raise ValueError("Relation strategy directives must provide a MergeStrategy")
        resolved_relation = strategies.resolve_relation(
            strategy,
            relation_name=relation_name,
            source=source,
            target=target,
            options=directive.options,
        )
        if resolved_relation is strategies.UNCHANGED or resolved_relation is None:
            return {"action": RELATION_ACTION_STRATEGY, "updated": 0}
        resolved_list = list(resolved_relation)
        if not dry_run:
            manager = getattr(target, relation_name)
            manager.set(resolved_list)
        return {
            "action": RELATION_ACTION_STRATEGY,
            "updated": len(resolved_list),
        }

    if directive.action == RELATION_ACTION_REASSIGN and isinstance(
        field, (ForeignObjectRel, OneToOneRel)
    ):
        return _reassign_related_objects(
            field=field,
            relation_name=relation_name,
            source=source,
            target=target,
            dry_run=dry_run,
            options=directive.options,
        )

    if directive.action == RELATION_ACTION_MERGE and isinstance(
        field, (ManyToManyRel, ManyToManyField)
    ):
        return _merge_many_to_many(
            field=field,
            relation_name=relation_name,
            source=source,
            target=target,
            dry_run=dry_run,
            options=directive.options,
        )

    if directive.action == RELATION_ACTION_CUSTOM and callable(directive.callback):
        return directive.callback(
            relation_name=relation_name,
            field=field,
            source=source,
            target=target,
            dry_run=dry_run,
            options=directive.options,
        )

    return None


def _relation_strategy_log_payload(directive: RelationDirective) -> Dict[str, Any]:
    """Serialise ``directive`` for merge logging purposes."""

    payload: Dict[str, Any] = {"action": directive.action}

    if directive.action == RELATION_ACTION_STRATEGY:
        strategy = directive.options.get("strategy")
        if isinstance(strategy, MergeStrategy):
            payload["strategy"] = strategy.value

    option_payload = {
        key: value
        for key, value in directive.options.items()
        if key != "strategy"
    }
    if option_payload:
        payload["options"] = strategies.serialise_options(option_payload)

    if directive.action == RELATION_ACTION_CUSTOM:
        payload["callback"] = _serialise_callable(directive.callback)

    return payload


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
    source_pk: Any,
    target: MergeMixin,
    user: Any,
    resolved_fields: Mapping[str, Any],
    relation_actions: Mapping[str, Mapping[str, Any]],
    strategy_map: Mapping[str, Any],
    source_snapshot: Mapping[str, Any] | None,
    target_before: Mapping[str, Any],
    target_after: Mapping[str, Any],
) -> None:
    from cms.models import MergeLog  # Imported lazily to avoid circular imports.

    content_type = ContentType.objects.get_for_model(target, for_concrete_model=True)
    serialised_resolved_fields = _serialise_value(resolved_fields)
    serialised_relation_actions = _serialise_value(relation_actions)
    serialised_strategy_map = _serialise_value(strategy_map)
    serialised_source_snapshot = _serialise_value(source_snapshot)
    serialised_target_before = _serialise_value(target_before)
    serialised_target_after = _serialise_value(target_after)
    MergeLog.objects.create(
        model_label=f"{content_type.app_label}.{content_type.model}",
        source_pk=source_pk,
        target_pk=target.pk,
        resolved_values={
            "fields": serialised_resolved_fields,
            "relations": serialised_relation_actions,
        },
        strategy_map=serialised_strategy_map,
        relation_actions=serialised_relation_actions,
        source_snapshot=serialised_source_snapshot,
        target_before=serialised_target_before,
        target_after=serialised_target_after,
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
    source_pk_value = source.pk
    base_strategies: MutableMapping[str, Any] = {
        "fields": getattr(model_cls, "merge_fields", {}) or {},
        "relations": getattr(model_cls, "relation_strategies", {}) or {},
    }
    effective_strategy = _deep_merge(base_strategies, strategy_map or {})

    field_strategy_overrides = effective_strategy.get("fields", {}) or {}
    resolver = strategies.StrategyResolver(model_cls, field_strategy_overrides)

    resolved_fields: Dict[str, strategies.StrategyResolution] = {}
    resolved_field_payloads: Dict[str, Any] = {}
    relation_actions: Dict[str, Dict[str, Any]] = {}

    strategy_log: Dict[str, Any] = {"fields": {}, "relations": {}}
    field_strategy_log = cast(Dict[str, Any], strategy_log["fields"])
    relation_strategy_overrides = effective_strategy.get("relations", {})

    for field_name in resolver.iter_field_names():
        field_strategy_log[field_name] = resolver.log_payload(field_name)

    source_snapshot = serialize_model_state(source) if archive else None
    target_before = serialize_model_state(target)
    relation_strategy_log: Dict[str, Any] = {}
    processed_relation_names: set[str] = set()

    with transaction.atomic():
        for field_name in resolver.iter_field_names():
            resolution = resolver.resolve_field(field_name, source=source, target=target)
            if resolution.value is strategies.UNCHANGED:
                if resolution.note:
                    resolved_field_payloads[field_name] = resolution.as_log_payload()
                continue
            resolved_fields[field_name] = resolution
            resolved_field_payloads[field_name] = resolution.as_log_payload()
            setattr(target, field_name, resolution.value)

        update_fields = list(resolved_fields.keys())
        if update_fields and not dry_run:
            target.save(update_fields=update_fields)

        for relation_field in source._meta.get_fields():
            relation_name: Optional[str] = None

            if isinstance(relation_field, ManyToManyField):
                relation_name = relation_field.name
            elif isinstance(relation_field, ManyToManyRel):
                try:
                    relation_name = relation_field.get_accessor_name()
                except AttributeError:
                    relation_name = None
            elif isinstance(relation_field, OneToOneRel):
                try:
                    relation_name = relation_field.get_accessor_name()
                except AttributeError:
                    relation_name = None
            elif isinstance(relation_field, ForeignObjectRel):
                try:
                    relation_name = relation_field.get_accessor_name()
                except AttributeError:
                    relation_name = None

            if not relation_name:
                continue
            if relation_name in processed_relation_names:
                continue

            if isinstance(relation_field, ForeignObjectRel) and not relation_field.auto_created:
                continue
            if isinstance(relation_field, OneToOneRel) and not relation_field.auto_created:
                continue

            raw_spec = None
            if isinstance(relation_strategy_overrides, Mapping):
                raw_spec = relation_strategy_overrides.get(relation_name)
            directive = _normalise_relation_spec(relation_field, raw_spec)

            relation_strategy_log[relation_name] = _relation_strategy_log_payload(directive)
            processed_relation_names.add(relation_name)

            result = _apply_relation_directive(
                directive=directive,
                field=relation_field,
                relation_name=relation_name,
                source=source,
                target=target,
                dry_run=dry_run,
            )
            if result:
                relation_actions[relation_name] = dict(result)

        if isinstance(relation_strategy_overrides, Mapping):
            for name in relation_strategy_overrides:
                if name not in relation_strategy_log:
                    relation_strategy_log[name] = {
                        "action": "unresolved",
                        "reason": "relation_not_found",
                    }

        strategy_log["relations"] = relation_strategy_log

        if not dry_run:
            if archive:
                target.archive_source_instance(source)
            if source.pk:
                source.delete()

        target_after = serialize_model_state(target if dry_run else model_cls.objects.get(pk=target.pk))

        if not dry_run:
            _log_merge(
                source_pk=source_pk_value,
                target=target,
                user=user,
                resolved_fields=resolved_field_payloads,
                relation_actions=relation_actions,
                strategy_map=strategy_log,
                source_snapshot=source_snapshot,
                target_before=target_before,
                target_after=target_after,
            )

            target.refresh_from_db()

    return MergeResult(
        target=target,
        resolved_values=resolved_fields,
        relation_actions=relation_actions,
    )
