# Merge implementation reference (Field Selection + Element)

This note supplements the merge engine docs with Element specifics and QA guidance for the new FIELD_SELECTION defaults.

## Architecture and strategy maps
- **Models**: Merge-enabled models subclass `MergeMixin` and declare `merge_fields` plus `relation_strategies`. Element uses the FIELD_SELECTION strategy for `name` and `parent_element` to avoid accidental hierarchy changes.【F:app/cms/models.py†L1479-L1486】
- **Strategy map construction**: `merge_elements` accepts a ``selected_fields`` mapping and delegates to `build_element_strategy_map`, which validates allowed keys, normalises parent choices (instance or PK), guards against cycles, and emits the per-field strategy payload consumed by `merge_records`.【F:app/cms/merge/element.py†L35-L85】【F:app/cms/merge/services.py†L11-L36】
- **Execution**: `merge_records` applies field strategies, moves relations according to `relation_strategies`, archives the source when not `dry_run`, and writes `MergeLog` plus django-simple-history entries for auditability. Dry runs skip writes and logging so QA can validate selections safely.【F:app/cms/merge/engine.py†L585-L739】

## Testing and coverage
- Preferred commands (run from repo root):
  - `python app/manage.py check`
  - `python app/manage.py makemigrations --check`
  - `python -m pytest app/cms/tests/test_element_merge.py app/cms/tests/test_element_merge_service.py app/cms/tests/test_element_merge_views.py app/cms/tests/test_element_merge_templates.py app/cms/tests/test_element_admin_merge.py`
- New tests cover invalid field selections, explicit parent PKs, dry-run safety, service-level strategy mapping, view permissions, template rendering, and admin actions; aggregate coverage stays above 90% for the Element merge additions.【F:app/cms/tests/test_element_merge.py†L1-L57】【F:app/cms/tests/test_element_merge_service.py†L1-L48】【F:app/cms/tests/test_element_merge_views.py†L1-L191】【F:app/cms/tests/test_element_merge_templates.py†L1-L148】【F:app/cms/tests/test_element_admin_merge.py†L1-L188】

## Rollback and safeguards
- **Dry run first**: use the field-selection form with `dry_run=True` in dev to validate choices without persisting changes or generating `MergeLog` entries.【F:app/cms/merge/element.py†L68-L85】【F:app/cms/merge/engine.py†L700-L739】
- **DB safety**: Element merges reject self-merges, identical candidates, and parent cycles; any `ValidationError` leaves source/target untouched so rollback is usually unnecessary beyond repeating the merge with corrected inputs.【F:app/cms/merge/element.py†L12-L33】【F:app/cms/merge/services.py†L22-L35】
- **History**: Successful merges create django-simple-history revisions and `MergeLog` rows; reverting can be done by restoring the previous history version or replaying snapshots recorded in the log if needed. No schema migrations were added for Element merge QA.
