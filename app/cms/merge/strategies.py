"""Strategy handlers used by the merge engine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator, Mapping, MutableMapping

from django.conf import settings
from django.db.models import Model
from django.utils.module_loading import import_string

from .constants import DEFAULT_FIELD_STRATEGY, MergeStrategy


class _Sentinel:
    """Unique sentinel object used to signal that a value should remain unchanged."""

    __slots__ = ()


UNCHANGED = _Sentinel()


class PendingResolution(RuntimeError):
    """Raised when a strategy requires manual intervention."""


@dataclass(frozen=True)
class StrategyResolution:
    """Normalized response returned by strategy handlers."""

    value: Any
    note: str | None = None

    def as_log_payload(self) -> Mapping[str, Any]:
        """Return a JSON serialisable payload for logging purposes."""

        payload: MutableMapping[str, Any] = {}
        if self.value is not UNCHANGED:
            payload["value"] = self.value
        else:
            payload["status"] = "unchanged"
        if self.note:
            payload["note"] = self.note
        return payload


class BaseStrategy:
    """Base class for field level strategy handlers."""

    def __call__(
        self,
        *,
        field_name: str,
        source: Model,
        target: Model,
        source_value: Any,
        target_value: Any,
        options: Mapping[str, Any],
    ) -> StrategyResolution:
        raise NotImplementedError


class LastWriteStrategy(BaseStrategy):
    """Always prefer the value provided by the source record."""

    def __call__(
        self,
        *,
        field_name: str,
        source: Model,
        target: Model,
        source_value: Any,
        target_value: Any,
        options: Mapping[str, Any],
    ) -> StrategyResolution:
        note = options.get("note") or f"Copied '{field_name}' from source record."
        return StrategyResolution(value=source_value, note=note)


class PreferNonNullStrategy(BaseStrategy):
    """Select the first non-empty value based on the configured priority order."""

    DEFAULT_PRIORITY: tuple[str, ...] = ("target", "source")

    def __call__(
        self,
        *,
        field_name: str,
        source: Model,
        target: Model,
        source_value: Any,
        target_value: Any,
        options: Mapping[str, Any],
    ) -> StrategyResolution:
        priority = self._normalise_priority(options.get("priority") or options.get("order"))
        for candidate in priority:
            if candidate == "source" and _is_truthy(source_value):
                note = options.get("note") or "Selected source value based on priority ordering."
                return StrategyResolution(value=source_value, note=note)
            if candidate == "target" and _is_truthy(target_value):
                note = options.get("note") or "Kept target value based on priority ordering."
                return StrategyResolution(value=target_value, note=note)

        # Fallback: honour default semantics when explicit priority does not resolve.
        if _is_truthy(target_value):
            note = options.get("note") or "Retained existing target value (no non-null source)."
            return StrategyResolution(value=target_value, note=note)
        if _is_truthy(source_value):
            note = options.get("note") or "Adopted source value (target empty)."
            return StrategyResolution(value=source_value, note=note)

        note = options.get("note") or "No non-null values available; leaving target unchanged."
        return StrategyResolution(value=target_value, note=note)

    def _normalise_priority(self, value: Any) -> tuple[str, ...]:
        if not value:
            return self.DEFAULT_PRIORITY
        if isinstance(value, str):
            parts = [segment.strip().lower() for segment in value.split(",") if segment.strip()]
        else:
            parts = [str(item).strip().lower() for item in value if str(item).strip()]
        normalised = [part for part in parts if part in {"source", "target"}]
        if not normalised:
            return self.DEFAULT_PRIORITY
        return tuple(dict.fromkeys(normalised))


class ConcatenateTextStrategy(BaseStrategy):
    """Combine unique text fragments from the target and source values."""

    DEFAULT_DELIMITER = " \u2014 "

    def __call__(
        self,
        *,
        field_name: str,
        source: Model,
        target: Model,
        source_value: Any,
        target_value: Any,
        options: Mapping[str, Any],
    ) -> StrategyResolution:
        delimiter = str(options.get("delimiter", self.DEFAULT_DELIMITER))
        unique_parts: list[str] = []

        for raw in (target_value, source_value):
            if raw is None:
                continue
            text = str(raw).strip()
            if not text:
                continue
            if text not in unique_parts:
                unique_parts.append(text)

        if not unique_parts:
            note = options.get("note") or "No text fragments available; leaving value unchanged."
            return StrategyResolution(value=target_value, note=note)

        concatenated = delimiter.join(unique_parts)
        if concatenated == target_value:
            note = options.get("note") or "Result matches existing target value; no change required."
        else:
            note = options.get("note") or f"Concatenated {len(unique_parts)} values using '{delimiter}'."
        return StrategyResolution(value=concatenated, note=note)


class WhitelistStrategy(BaseStrategy):
    """Only update fields that appear in the configured allow-list."""

    def __call__(
        self,
        *,
        field_name: str,
        source: Model,
        target: Model,
        source_value: Any,
        target_value: Any,
        options: Mapping[str, Any],
    ) -> StrategyResolution:
        raw_allow = options.get("allow") or options.get("allowed") or options.get("fields")
        if isinstance(raw_allow, str):
            allow_values = [item.strip() for item in raw_allow.split(",") if item.strip()]
        else:
            allow_values = list(raw_allow or [])
        allow_set = set(allow_values)
        if allow_set and field_name not in allow_set:
            note = options.get("note") or f"Field '{field_name}' not in whitelist; no changes applied."
            return StrategyResolution(value=UNCHANGED, note=note)

        if _is_truthy(source_value):
            note = options.get("note") or "Source value allowed by whitelist."
            return StrategyResolution(value=source_value, note=note)

        note = options.get("note") or "Whitelist allowed field but source value empty; retained target value."
        return StrategyResolution(value=target_value, note=note)


class FieldSelectionStrategy(BaseStrategy):
    """Use an explicit user-selected value for the field when provided."""

    def __call__(
        self,
        *,
        field_name: str,
        source: Model,
        target: Model,
        source_value: Any,
        target_value: Any,
        options: Mapping[str, Any],
    ) -> StrategyResolution:
        explicit_key = None
        if "value" in options:
            explicit_key = "value"
        elif "selected_value" in options:
            explicit_key = "selected_value"
        if explicit_key:
            note = options.get("note") or "Applied user-selected value."
            return StrategyResolution(value=options.get(explicit_key), note=note)

        selected_from_raw = options.get("selected_from") or options.get("choice")
        selected_from = str(selected_from_raw).strip().lower() if selected_from_raw else ""

        if selected_from == "source":
            note = options.get("note") or f"User selected source value for '{field_name}'."
            return StrategyResolution(value=source_value, note=note)

        if selected_from == "target":
            note = options.get("note") or f"User kept target value for '{field_name}'."
            return StrategyResolution(value=target_value, note=note)

        note = options.get("note") or "No user selection provided; leaving value unchanged."
        return StrategyResolution(value=UNCHANGED, note=note)


class CustomStrategy(BaseStrategy):
    """Delegate resolution to a project specific callable."""

    def __init__(self, registry: "StrategyResolver") -> None:
        self._registry = registry

    def __call__(
        self,
        *,
        field_name: str,
        source: Model,
        target: Model,
        source_value: Any,
        target_value: Any,
        options: Mapping[str, Any],
    ) -> StrategyResolution:
        handler, cleaned_options = self._registry.get_custom_handler(field_name, options)
        result = handler(
            field_name=field_name,
            source=source,
            target=target,
            source_value=source_value,
            target_value=target_value,
            options=cleaned_options,
        )
        return _coerce_resolution(result)


class UserPromptStrategy(BaseStrategy):
    """Placeholder strategy that requires manual intervention."""

    def __call__(
        self,
        *,
        field_name: str,
        source: Model,
        target: Model,
        source_value: Any,
        target_value: Any,
        options: Mapping[str, Any],
    ) -> StrategyResolution:  # pragma: no cover - exercised indirectly
        raise PendingResolution(
            f"Field '{field_name}' requires manual resolution before merge can proceed."
        )


def serialise_options(options: Mapping[str, Any]) -> MutableMapping[str, Any]:
    """Return a JSON serialisable copy of ``options`` suitable for logging."""

    serialised: MutableMapping[str, Any] = {}
    for key, value in options.items():
        if isinstance(value, set):
            serialised[key] = sorted(value)
        elif isinstance(value, MergeStrategy):
            serialised[key] = value.value
        elif callable(value):
            module = getattr(value, "__module__", "")
            qualname = getattr(value, "__qualname__", getattr(value, "__name__", repr(value)))
            serialised[key] = f"{module}.{qualname}".strip(".")
        else:
            serialised[key] = value
    return serialised


class StrategyResolver:
    """Resolve field strategies for a model instance."""

    def __init__(
        self,
        model_cls: type[Model],
        field_strategies: Mapping[str, Any] | None = None,
    ) -> None:
        self.model_cls = model_cls
        self.model_label = model_cls._meta.label
        self._raw_strategies = dict(field_strategies or {})
        self._model_defaults = dict(getattr(model_cls, "merge_fields", {}) or {})
        self._field_order = list(
            dict.fromkeys(
                [*self._raw_strategies.keys(), *self._model_defaults.keys()]
            )
        )
        self._custom_callables: dict[str, Callable[..., Any]] = {}
        self._normalised: dict[str, tuple[MergeStrategy, Mapping[str, Any], Mapping[str, Any]]] = {}

        self._handlers: dict[MergeStrategy, BaseStrategy] = {
            MergeStrategy.LAST_WRITE: LastWriteStrategy(),
            MergeStrategy.PREFER_NON_NULL: PreferNonNullStrategy(),
            MergeStrategy.CONCAT_TEXT: ConcatenateTextStrategy(),
            MergeStrategy.WHITELIST: WhitelistStrategy(),
            MergeStrategy.FIELD_SELECTION: FieldSelectionStrategy(),
            MergeStrategy.CUSTOM: CustomStrategy(self),
            MergeStrategy.USER_PROMPT: UserPromptStrategy(),
        }

    def iter_field_names(self) -> Iterator[str]:
        """Return the list of field names that the resolver knows about."""

        return iter(self._field_order)

    def resolve_field(
        self,
        field_name: str,
        *,
        source: Model,
        target: Model,
    ) -> StrategyResolution:
        """Resolve ``field_name`` using the configured strategy map."""

        strategy, options, _ = self._get_strategy(field_name)
        handler = self._handlers.get(strategy)
        if not handler:
            raise ValueError(f"Unsupported merge strategy: {strategy}")

        source_value = getattr(source, field_name, None)
        target_value = getattr(target, field_name, None)

        return handler(
            field_name=field_name,
            source=source,
            target=target,
            source_value=source_value,
            target_value=target_value,
            options=options,
        )

    def log_payload(self, field_name: str) -> Mapping[str, Any]:
        """Return a serialisable payload describing the strategy for ``field_name``."""

        strategy, _, log_options = self._get_strategy(field_name)
        payload: MutableMapping[str, Any] = {"strategy": strategy.value}
        if log_options:
            payload["options"] = serialise_options(log_options)
        return payload

    def get_custom_handler(
        self,
        field_name: str,
        options: Mapping[str, Any],
    ) -> tuple[Callable[..., Any], Mapping[str, Any]]:
        """Return the callable that should handle custom strategy resolution."""

        if field_name in self._custom_callables:
            return self._custom_callables[field_name], options

        handler_spec = None
        for key in ("handler", "callback", "callable"):
            if key in options:
                handler_spec = options[key]
                break

        if handler_spec is None:
            custom_settings = getattr(settings, "MERGE_CUSTOM_STRATEGIES", {}) or {}
            model_config = custom_settings.get(self.model_label, {})
            handler_spec = model_config.get(field_name)

        if handler_spec is None:
            raise ValueError(
                f"No custom strategy registered for {self.model_label}.{field_name}"
            )

        if isinstance(handler_spec, str):
            handler = import_string(handler_spec)
        elif callable(handler_spec):
            handler = handler_spec
        else:
            raise TypeError("Custom strategy handler must be a callable or dotted path string")

        self._custom_callables[field_name] = handler
        cleaned = {
            key: value
            for key, value in options.items()
            if key not in {"handler", "callback", "callable"}
        }
        return handler, cleaned

    def _get_strategy(
        self, field_name: str
    ) -> tuple[MergeStrategy, Mapping[str, Any], Mapping[str, Any]]:
        if field_name in self._normalised:
            return self._normalised[field_name]

        raw_spec = self._raw_strategies.get(field_name)
        if raw_spec is None:
            raw_spec = self._model_defaults.get(field_name, DEFAULT_FIELD_STRATEGY)

        strategy, options = _normalize_strategy_spec(raw_spec)
        log_options: Mapping[str, Any] = options

        if strategy is MergeStrategy.CUSTOM:
            handler, cleaned = self.get_custom_handler(field_name, options)
            self._custom_callables[field_name] = handler
            log_options = options
            options = cleaned

        self._normalised[field_name] = (strategy, options, log_options)
        return self._normalised[field_name]


def _normalize_strategy_spec(value: Any) -> tuple[MergeStrategy, Mapping[str, Any]]:
    if isinstance(value, Mapping):
        if "strategy" not in value:
            raise ValueError("Strategy mapping must include a 'strategy' key")
        strategy = MergeStrategy(value["strategy"])
        options = {k: v for k, v in value.items() if k != "strategy"}
        return strategy, options
    return MergeStrategy(value), {}


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
        return source_values

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
        raise PendingResolution(
            f"Relation '{relation_name}' requires manual resolution before merge can proceed."
        )

    raise ValueError(f"Unsupported merge strategy for relation: {strategy}")


def _coerce_resolution(value: Any) -> StrategyResolution:
    if isinstance(value, StrategyResolution):
        return value
    if isinstance(value, tuple) and len(value) == 2:
        return StrategyResolution(value=value[0], note=value[1])
    return StrategyResolution(value=value)


def _is_truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


__all__ = [
    "StrategyResolver",
    "StrategyResolution",
    "PendingResolution",
    "UNCHANGED",
    "resolve_relation",
    "serialise_options",
]

