# Merge architecture overview

This document summarises the current merge tool components to support strategy updates.

## Core primitives

- `MergeStrategy` (app/cms/merge/constants.py) defines supported strategies for field and relation handling with defaults `DEFAULT_FIELD_STRATEGY` (`prefer_non_null`) and `DEFAULT_RELATION_STRATEGY` (`last_write`).
- `MergeMixin` (app/cms/merge/mixins.py) is the base for mergeable models and exposes `merge_fields`, `relation_strategies`, `get_merge_display_fields`, and hooks such as `archive_source_instance` for post-merge archiving.
- The merge registry (`register_merge_rules` in app/cms/merge/registry.py) stores per-model field and relation strategies in `MERGE_REGISTRY` and merges them into model-level `merge_fields`/`relation_strategies` when the `MERGE_TOOL_FEATURE` flag is enabled.

## Strategy resolution

- `StrategyResolver` (app/cms/merge/strategies.py) normalises effective field strategies combining overrides and model defaults. It supports built-in handlers (`LastWriteStrategy`, `PreferNonNullStrategy`, `ConcatenateTextStrategy`, `WhitelistStrategy`) plus `CustomStrategy` and `UserPromptStrategy` sentinels.
- `_normalize_strategy_spec` coerces raw mappings or enum/string values into `(MergeStrategy, options)` pairs, while `_coerce_resolution` standardises handler return values into `StrategyResolution` objects with optional notes and an `UNCHANGED` sentinel.
- Relation strategies are normalised through `resolve_relation` for M2M sets and `_normalise_relation_spec` in the engine for FK/one-to-one relations, supporting default actions (`reassign`, `merge`, `skip`) or explicit `MergeStrategy` payloads.

## Merge execution flow

- `merge_records` (app/cms/merge/engine.py) orchestrates merges under `transaction.atomic()`, validating source/target types, combining base strategies from the model with runtime overrides, and driving `StrategyResolver` to collect field-level resolutions.
- Resolved field values are applied with `target.save(update_fields=...)` when not a dry run. Relation handling iterates through auto-created relations, applies directives from `_normalise_relation_spec`, and records actions.
- Merge results are logged via `_log_merge`, creating `MergeLog` entries with snapshots (`serialize_model_state`) of source and target before/after merge, the strategy map, and relation actions. The source record may be archived via `archive_source_instance` before deletion when `archive=True`.

## Views and entry points

- Administrative entry points live in `MergeCandidateAdminView` and `MergeCandidateAPIView` (app/cms/views.py) gated by `MERGE_TOOL_FEATURE` and staff checks. The admin view lists merge-enabled models from `MERGE_REGISTRY`, and the API provides fuzzy candidate results using `score_candidates` to feed the merge UI.

## Integration considerations for new strategies

- New per-field strategies should plug into `MergeStrategy`/`StrategyResolver` or be exposed via `MergeMixin.merge_fields` and the registry, ensuring any custom callables are discoverable via `MERGE_CUSTOM_STRATEGIES` settings when using `MergeStrategy.CUSTOM`.
- Relation behaviour for new flows should respect `_default_relation_action` and `_apply_relation_directive` expectations to keep logging and MergeLog payloads consistent.
