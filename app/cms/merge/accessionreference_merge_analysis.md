# AccessionReference merge analysis

## Model structure
- **Relationships**: joins `Accession` and `Reference` via required foreign keys; both cascade on delete, so merges must reassign dependents before removing any source rows to avoid unintended deletes.
- **Fields**: optional `page` (`CharField`, max_length 10) in addition to timestamps/user tracking from `BaseModel`.
- **Integrity**: unique constraint on `(accession, reference)` prevents duplicate links for the same pair.
- **History**: `HistoricalRecords` already enabled, so merge operations should preserve history consistency and emit audit entries for updates/deletes.

## Admin configuration
- Registered through `AccessionReferenceAdmin` using `HistoricalImportExportAdmin` with list display/search on accession and reference fields.
- No merge mixins (`MergeAdminMixin`/`MergeAdminActionMixin`) are attached, and the changelist currently lacks any merge action or URL hook.

## Existing merge tooling to reuse
- Merge infrastructure lives under `app/cms/merge/` with `MergeStrategy.FIELD_SELECTION`, registry helpers, and admin forms/actions that already support FieldSlip, Reference, Storage, and Element.
- `MergeAdminForm` dynamically builds per-field strategy selectors and manual value inputs; `MergeAdminMixin` supplies admin URLs/templates, while `MergeAdminActionMixin` wires bulk actions on changelists when the merge feature flag is enabled.

## Observations & gaps for AccessionReference merges
- `AccessionReference` does not implement `MergeMixin` or `merge_fields`, so it is not yet eligible for the merge registry or strategy resolution.
- There are no relation strategies defined for reassigning dependent objects (e.g., anything referencing `AccessionReference`), and no admin wiring to initiate merges from `admin/cms/accessionreference/`.
- Import/export flows (including importer, OCR processing, and resources) rely on this model, so merge routines must keep unique `(accession, reference)` pairs intact and preserve downstream history records.
