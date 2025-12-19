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
- **Forms**: `AccessionReferenceMergeSelectionForm` (candidate + target chooser) and `AccessionReferenceFieldSelectionForm` (per-field strategy builder) live in `cms.forms`. They mirror the generic `FieldSelectionForm` API used elsewhere and preserve ordering of chosen candidates so the review UI can respect user intent.
- **Services**: `build_accession_reference_field_selection_form`, `build_accession_reference_strategy_map`, and `merge_accession_reference_candidates` in `cms.merge.services` wrap strategy creation and merge execution; they already enforce “same accession” constraints and translate `reference`/`page` selections into `MergeStrategy.FIELD_SELECTION` payloads.
- **Views/URLs/Templates**: The generic merge UI under `cms/merge/` (`FieldSelectionMergeView`, `merge/per_field_strategy.html`, `merge/urls.py`) is already wired for Element merges and can be pointed at any `MergeMixin` model. Accession references can plug into this flow with minimal glue: a model-level `merge_fields` definition and a `MergeMixin` subclass unlock the existing JSON + HTML interactions.
- Merge infrastructure lives under `app/cms/merge/` with `MergeStrategy.FIELD_SELECTION`, registry helpers, and admin forms/actions that already support FieldSlip, Reference, Storage, and Element.
- `MergeAdminForm` dynamically builds per-field strategy selectors and manual value inputs; `MergeAdminMixin` supplies admin URLs/templates, while `MergeAdminActionMixin` wires bulk actions on changelists when the merge feature flag is enabled.

## Observations & gaps for AccessionReference merges
- `AccessionReference` does not implement `MergeMixin` or `merge_fields`, so it is not yet eligible for the merge registry or strategy resolution.
- There are no relation strategies defined for reassigning dependent objects (e.g., anything referencing `AccessionReference`), and no admin wiring to initiate merges from `admin/cms/accessionreference/`.
- There is no accession-facing merge UI yet. The existing pattern (e.g., element merges) suggests reusing: a “Merge references” CTA beside the list header, a selection form posting candidate IDs + target to the per-field strategy view, and a review/confirm screen backed by `AccessionReferenceFieldSelectionForm`.
- Import/export flows (including importer, OCR processing, and resources) rely on this model, so merge routines must keep unique `(accession, reference)` pairs intact and preserve downstream history records.
