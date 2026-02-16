# Element merge analysis

## Element model structure
- **Fields**: `name` (`CharField`, required, 255 chars), `parent_element` (self-referential `ForeignKey`, `CASCADE`, nullable/blank), plus `created_on/modified_on` and user tracking from `BaseModel`.
- **History**: `HistoricalRecords` enabled; merge flows must preserve audit entries.
- **Hierarchy & cascading**: deleting a parent cascades to children; merge routines should reparent children before deleting sources to avoid cascade loss.
- **Ordering**: default ordering by `parent_element__name` then `name`; any merge-created records should respect this natural ordering.
- **Validation hooks**: `BaseModel.clean()` requires an authenticated user; service-level merges must set the request user context to avoid validation errors.

## Existing merge patterns to reuse
- **`MergeMixin` and `merge_fields`** on FieldSlip, Reference, and Storage illustrate FIELD_SELECTION usage via `MergeStrategy.FIELD_SELECTION` mappings and relation strategies for reassigning dependents.
- **Strategy engine** in `app/cms/merge/strategies.py` supports FIELD_SELECTION and other strategies; Element merge should register its fields using `MergeStrategy.FIELD_SELECTION` via the registry.
- **Registry helper** in `app/cms/merge/registry.py` populates model-level `merge_fields`/`relation_strategies` when `MERGE_TOOL_FEATURE` is enabled; Element should follow the same registration flow.
- **History awareness**: existing MergeMixin models rely on django-simple-history to capture changes; Element merges must continue to emit history entries for traceability.

## Observations & gaps
- Element currently does **not** inherit `MergeMixin`, so merge eligibility and field strategy registration need to be added during implementation.
- No unique constraints on `name` + `parent_element`; duplicates may exist. Merge logic should handle deduplication cautiously and avoid accidental uniqueness assumptions.
- The self-referential hierarchy implies relation strategies for `children` must be defined to prevent orphaned or deleted descendants during merges.
