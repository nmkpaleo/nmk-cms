# Identification taxonomy unification design

## Goals and constraints
- Preserve ability to capture free-text determinations when no controlled `Taxon` exists.
- Prefer a single authoritative linkage to `Taxon` to simplify filters, search, admin, and utility lookups.
- Maintain backward compatibility for historical data and imports while migrating safely on MySQL.
- Keep django-simple-history tracking intact and avoid breaking existing APIs/forms during rollout.

## Recommended unified representation
Use a single nullable `ForeignKey` to `Taxon` named `taxon_record` for structured linkage plus a companion required verbatim text field `taxon_verbatim` (renamed from current `taxon` CharField) to preserve human-entered names. The authoritative taxonomic context is driven by `taxon_record` when present; `taxon_verbatim` always stores the user-provided string at time of identification.

### Field definitions
- `taxon_record = models.ForeignKey(Taxon, null=True, blank=True, on_delete=models.PROTECT, related_name="identifications")`
  - Restrict queryset to accepted taxa (`TaxonStatus.ACCEPTED`) in forms/serializers.
  - Add DB index for filtering and joins.
- `taxon_verbatim = models.CharField(max_length=<existing length>, blank=True)`
  - Must be non-empty on save; populated from `taxon_record.taxon_name` when FK is chosen and no verbatim text was provided.
  - Add simple case-insensitive index if supported to keep free-text search performant (optional depending on MySQL collation).
- Deprecated accessors: retain `taxon` property for backward compatibility during transition, mapping to `taxon_verbatim` with deprecation warnings in code paths (no DB column).

## Acceptance criteria
- Identification creation/edit supports selecting a controlled `Taxon` **or** supplying only verbatim text.
- When a `Taxon` is selected, the derived higher taxonomy is available through relationships (family, genus, etc.) without additional queries beyond standard `select_related` usage.
- Free-text-only entries remain valid and searchable; filters and reports gracefully handle missing `taxon_record`.
- Admin, filters, and utilities prefer `taxon_record` when set; otherwise fall back to `taxon_verbatim`.
- Data migration preserves all existing values with no loss; rollback migration restores previous schema and values.
- History records capture changes to both fields; audit trails remain intact.

## Validation rules
- Verbatim text is required (non-empty) even when `taxon_record` is provided; default to FK name if not supplied.
- `taxon_record` optional but, when set, must point to accepted taxa only (enforced via form/serializer validation and clean method).
- Prevent conflicting inputs: if `taxon_record` is set and `taxon_verbatim` differs only by case/spacing, normalize whitespace but store original casing; allow deliberate divergence for typos with an explicit warning message in forms.
- During migration, normalize leading/trailing whitespace on `taxon` into `taxon_verbatim` but do not alter internal casing.

## Migration strategy
1. Add `taxon_verbatim` field alongside existing `taxon`/`taxon_record`; populate with existing `taxon` values or `taxon_record.taxon_name` when missing.
2. Backfill `taxon_record` by matching `taxon` values to `Taxon.taxon_name` (case-insensitive) where unique; log ambiguous matches to a review table or console output during migration dry-run (non-blocking).
3. Dual-write: update models/forms/serializers to keep `taxon` (legacy) and `taxon_verbatim` in sync while consumers are migrated.
4. Deprecate legacy `taxon` column: remove from forms/admin exports, keep read-only property; add DB constraint to prevent NULL in `taxon_verbatim`.
5. Final cleanup migration: drop `taxon` column after all consumers updated and monitoring confirms stability.

## Forms/serializers behavior
- Render a select2/autocomplete widget for `taxon_record` limited to accepted taxa; include a free-text input for `taxon_verbatim` with help text explaining precedence.
- In `clean()`, if `taxon_record` is set and `taxon_verbatim` empty, set verbatim to selected `taxon_record.taxon_name`.
- Expose `taxon_record_external_id` (via `Taxon.external_id`) for import/export parity.
- API serializers should return both `taxon_record` (PK and display) and `taxon_verbatim`; accept either a PK or `external_id` for the FK to ease integrations.

## Filters/search updates
- django-filter configurations should primarily filter on `taxon_record` relationships for hierarchical facets; include a fallback text filter on `taxon_verbatim` for free-text matches.
- Existing helper that attempts to match free-text to Taxon should remain as a secondary enrichment path but can be simplified once FK coverage increases.

## Admin considerations
- List/search on `taxon_record` (with related fields) and `taxon_verbatim`; remove reliance on `taxon__taxon_name` lookup that assumes a FK.
- Add list_filter to differentiate controlled vs. free-text identifications (e.g., `has_taxon_record` boolean).

## History/audit
- Ensure `HistoricalRecords` includes `taxon_record` and `taxon_verbatim`; migrate history models if necessary.
- During dual-write phase, record both legacy `taxon` and new fields to avoid audit gaps.

## Rollout and compatibility
- Feature-flag dual-write behavior to allow safe rollback (toggle to re-enable legacy `taxon` usage without data loss).
- Update docs (user/admin/development) and CHANGELOG with migration steps and rollback instructions.
- Coordinate with import/export processes so incoming data populates `taxon_verbatim` and optional `taxon_record` before removing legacy column.
