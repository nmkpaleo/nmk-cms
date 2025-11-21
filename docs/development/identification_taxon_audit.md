# Identification taxon field audit

## Model structure
- `Identification.taxon` is a nullable/blank `CharField` intended to hold the determined taxon name text.  It is not constrained to existing taxonomy records.  `Identification.taxon_record` is a nullable/blank `ForeignKey` to `Taxon` with help text describing it as a link to the controlled taxonomy and a `clean` validator restricting the relation to accepted taxa only via `TaxonStatus.ACCEPTED`.
- Other identification metadata includes `identified_by`, `reference`, `date_identified`, `identification_qualifier`, `verbatim_identification`, and `identification_remarks`, all tracked by `django-simple-history` through `HistoricalRecords`.
- The `Taxon` model stores canonical taxonomy fields (`taxon_name`, rank fields such as `family`, `genus`, `species`, etc.), status with synonym support, and hierarchy pointers (`parent`, `accepted_taxon`).

## Form behavior
- `AccessionRowIdentificationForm` exposes both `taxon` (free text) and `taxon_record` (select2/autocomplete widget). The `taxon_record` queryset is filtered to active accepted taxa, marked optional, and when present without a `taxon` value, the form populates `taxon` from `taxon_record.taxon_name` during `clean`.
- Validation for `identified_by` integrates widget-level pending errors; no additional validation links between `taxon` and `taxon_record` are enforced in the form beyond the auto-fill.

## Query/filter usage
- Accession filters look at both `Identification.taxon` and `Identification.taxon_record` for broad taxon search, including synonym names through `taxon_record__synonyms__taxon_name`.
- Family/subfamily/tribe/genus/species filters use `taxon_record` attribute lookups and also consider `Identification.taxon` when the free-text name matches helper-derived names for the given rank.

## Utility resolution
- `cms.utils.get_identification_metadata` builds taxonomy lookup maps preferring `taxon_record` when set. When missing, it attempts to match `taxon` free-text values (case-insensitive) against existing `Taxon.taxon_name` entries in bulk to populate taxonomy context.

## Admin/import surfaces
- `IdentificationAdmin` displays both `taxon` (free text) and `verbatim_identification` and allows searching via specimen number, verbatim text, `taxon` (configured as `taxon__taxon_name`), and identifier name; the search reference to `taxon__taxon_name` assumes relational traversal even though `taxon` is a `CharField`, which may limit search effectiveness until fields are unified.
- Import/export resource `IdentificationResource` exposes both `taxon` and `taxon_record`, mapping the latter via the `Taxon.external_id` using `ForeignKeyWidget`.

## Observations for unification
- Both fields are used throughout forms, filters, utilities, and admin. `taxon_record` enables richer taxonomy traversal and validation, while `taxon` preserves free-text or verbatim names and is used as a fallback for matching. Any unification must preserve free-text capture while maintaining accepted-taxonomy constraints and downstream filters that rely on structured attributes.
