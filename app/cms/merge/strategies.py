"""Strategy handlers used by the merge engine."""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from django.db.models import Model

from .constants import MergeStrategy


class _Sentinel:
    pass


UNCHANGED = _Sentinel()

def resolve_field(
    strategy: MergeStrategy,
    *,
    field_name: str,
    source: Model,
    target: Model,
    options: Mapping[str, Any] | None = None,
) -> Any:
    """Apply ``strategy`` to a concrete model field."""

    options = options or {}
    source_value = getattr(source, field_name, None)
    target_value = getattr(target, field_name, None)

    if strategy is MergeStrategy.LAST_WRITE:
        source_ts = getattr(source, "modified_on", None)
        target_ts = getattr(target, "modified_on", None)
        if source_ts and target_ts and source_ts > target_ts:
            return source_value
        return target_value

    if strategy is MergeStrategy.PREFER_NON_NULL:
        if _is_truthy(target_value):
            return target_value
        if _is_truthy(source_value):
            return source_value
        return target_value

    if strategy is MergeStrategy.CONCAT_TEXT:
        parts = []
        for value in (target_value, source_value):
            if value:
                text = str(value).strip()
                if text and text not in parts:
                    parts.append(text)
        return " \u2014 ".join(parts) if parts else target_value

    if strategy is MergeStrategy.WHITELIST:
        allowed = set(options.get("allow", []) or options.get("allowed", []))
        if allowed and field_name not in allowed:
            return UNCHANGED
        return target_value if _is_truthy(target_value) else source_value

    if strategy is MergeStrategy.CUSTOM:
        callback = options.get("callback")
        if not callable(callback):
            raise ValueError("Custom strategy requires a callable 'callback'")
        return callback(
            field_name=field_name,
            source=source,
            target=target,
            source_value=source_value,
            target_value=target_value,
            options=options,
        )

    if strategy is MergeStrategy.USER_PROMPT:
        raise NotImplementedError("User prompt strategy requires manual intervention")

    raise ValueError(f"Unsupported merge strategy: {strategy}")


def resolve_relation(
    strategy: MergeStrategy,
    *,
    relation_name: str,
    source: Model,
    target: Model,
    options: Mapping[str, Any] | None = None,
) -> Iterable[Any] | _Sentinel | None:
    """Apply ``strategy`` to a relation (typically many-to-many) field."""

    options = options or {}
    source_manager = getattr(source, relation_name)
    target_manager = getattr(target, relation_name)
    source_values = list(source_manager.values_list("pk", flat=True))
    target_values = list(target_manager.values_list("pk", flat=True))

    if strategy is MergeStrategy.LAST_WRITE:
        source_ts = getattr(source, "modified_on", None)
        target_ts = getattr(target, "modified_on", None)
        if source_ts and target_ts and source_ts > target_ts:
            return source_values
        return target_values

    if strategy is MergeStrategy.PREFER_NON_NULL:
        if target_values:
            return target_values
        if source_values:
            return source_values
        return target_values

    if strategy is MergeStrategy.CONCAT_TEXT:
        return list(dict.fromkeys([*target_values, *source_values]))

    if strategy is MergeStrategy.WHITELIST:
        allowed = set(options.get("allow", []) or options.get("allowed", []))
        if allowed:
            target_filtered = [pk for pk in target_values if pk in allowed]
            if target_filtered:
                return target_filtered
            source_filtered = [pk for pk in source_values if pk in allowed]
            if source_filtered:
                return source_filtered
            return []
        return target_values if target_values else source_values

    if strategy is MergeStrategy.CUSTOM:
        callback = options.get("callback")
        if not callable(callback):
            raise ValueError("Custom strategy requires a callable 'callback'")
        return callback(
            relation_name=relation_name,
            source=source,
            target=target,
            source_values=source_values,
            target_values=target_values,
            options=options,
        )

    if strategy is MergeStrategy.USER_PROMPT:
        raise NotImplementedError("User prompt strategy requires manual intervention")

    raise ValueError(f"Unsupported merge strategy for relation: {strategy}")


def _is_truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True
