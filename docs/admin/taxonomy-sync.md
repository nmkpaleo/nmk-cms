# Taxonomy Sync (NOW and GBIF)

This guide covers the administrative workflow for synchronising the CMS taxonomy with NOW mammal data and GBIF Catalogue of Life matches. The tooling lives inside the Django admin and provides a preview-first experience followed by a transactional apply step.

## Prerequisites

1. Ensure your account is staff-enabled and has the **`cms.can_sync`** permission on the `Taxon` model.
2. Confirm the NOW data sources are configured via environment variables:
   * `TAXON_NOW_ACCEPTED_URL`
   * `TAXON_NOW_SYNONYMS_URL`
   * `TAXON_SYNC_DEACTIVATE_MISSING` (optional, defaults to `true`) controls whether missing taxa are deactivated.
3. Verify migrations adding the Taxon schema changes and `TaxonomyImport` model have been applied.

## Accessing the sync UI

1. Navigate to **CMS → Taxa** inside the Django admin.
2. If you have permission, a **Sync Taxa Now** button appears beside the standard add button. Selecting it triggers the preview fetch.

## Which taxa are included

Sync uses names already present in the CMS:

- Existing `Taxon` records from any source, including taxa linked to drawers and identifications.
- Identification taxon text (`taxon_verbatim`, falling back to the legacy `taxon` field).
- Field-slip `verbatim_taxon` text.

Names must match the NOW name after ignoring case and normalizing whitespace.
A matching synonym also brings in its accepted taxon so the link can be stored.
An order or family entry does not import all of its descendants, and an accepted
name does not import all of its synonyms. With no local names, nothing is imported.

The complete NOW TSV files are still downloaded because they are bulk exports;
only the relevant records enter the preview and apply steps. Existing NOW records
remain eligible for updates and missing-record deactivation. Previously imported catalogue records remain in scope.

## Source selection and duplicate prevention

- GBIF checks each locally recorded name, using its rank when known.
- For Mammalia, NOW takes priority if the same name/rank is available there.
- For other classes, GBIF supplies the taxonomy. Mammals absent from NOW also use GBIF.
- A later NOW match updates a GBIF mammal row in place, preserving its ID and links.
- LEGACY rows are reused by name/rank. A normalized identity key prevents a second
  row with the same name/rank, regardless of source, authorship, or status.
- Synonyms link to the selected accepted record, including across sources.

Only exact GBIF name/rank matches with a class and no diagnostic issues are applied.
Uncertain matches and network failures appear in the preview issues; they do not
cause existing records to be deactivated. Successful changes can still be applied
when other names have issues; the import log marks that run as needing review.

The preview shows the source beside each proposed new name and reports source
changes on updates. GBIF IDs include the checklist key and usage key. GBIF source
versions are content hashes; NOW versions remain the export timestamp.

### Deployment migration

Migration 0088 consolidates existing duplicates before creating the uniqueness
constraint. It prefers NOW for mammals and GBIF for non-mammals, then reconnects
identifications, drawers, parent links, and synonym links to the surviving row.
Historical identification links are redirected, and historical taxon records are
retained. Previously ambiguous identifications are linked when a unique accepted
name (or synonym target) can be resolved. The consolidation is not reversed by
rolling the schema migration back; recovery of separate duplicate rows requires
restoring a backup.

### GBIF configuration

- `TAXON_GBIF_MATCH_URL`: defaults to `https://api.gbif.org/v2/species/match`.
- `TAXON_GBIF_CHECKLIST_KEY`: defaults to `7ddf754f-d193-4cc9-b351-99906754a03b` (COL XR).
- `TAXON_GBIF_TIMEOUT`: per-request timeout in seconds, default 15.

Matches are reused within a sync run. Preview and apply each fetch current data.
See the [GBIF matching documentation](https://techdocs.gbif.org/en/data-processing/taxonomy-interpretation).

## Understanding the preview

The preview page is a dry-run. No records are modified. It displays:

* **Summary cards** – total counts for records to create, update, deactivate, synonym links, and issues.
* **Accepted taxa sections** – tables describing accepted taxa that will be added or updated, including field-by-field changes.
* **Synonym changes** – highlights synonym creations and updates, and the accepted taxon each will link to.
* **Deactivations** – lists active records that will be set inactive if they no longer exist upstream (only when deactivation is enabled).
* **Issues** – any blocking problems such as synonyms referencing missing accepted taxa. Resolve these before applying the sync.

Use the preview to coordinate with data curators before making changes. You can close the page without side effects.

## Applying the sync

1. Review the preview carefully, especially the Issues section.
2. Click **Apply sync** to submit the form. The system immediately reuses the preview output, performing the upserts and deactivations in a single database transaction.
3. Upon completion you are redirected to a results page summarising the applied changes. A green success banner indicates all operations succeeded.
4. Follow the **View import log** link to audit the `TaxonomyImport` record. It captures counts, issue context, and the NOW source version that was applied.

If an exception occurs, the transaction is rolled back, a red alert banner is shown, and no data is changed. Re-run the preview once the underlying issue is resolved.

## Import logs

The Django admin registers a **Taxonomy Imports** section. Each sync produces a row containing:

* Source (`NOW_GBIF` for the combined sync, or `NOW` for NOW-only runs)
* Source version (NOW timestamp or commit hash)
* Started / finished timestamps
* A boolean `ok` flag
* JSON summaries of counts and issues

Import logs are managed by `django-simple-history`, allowing auditors to review past runs or revert metadata if necessary.

## Troubleshooting and rollback

| Problem | Resolution |
| --- | --- |
| Preview raises connection errors | Confirm the NOW URLs are correct and reachable. Retry once connectivity is restored. |
| Issues reported for missing accepted taxa | Contact the NOW data maintainers or postpone the sync until the dataset includes the referenced taxon. |
| Sync result shows `ok = False` | Investigate the associated import log. Successful changes may have been committed; inspect the report before retrying. |
| Need to undo a sync | Locate the relevant `TaxonomyImport`, export the list of affected taxa, and restore them from backups or re-run the sync after correcting the upstream data. Because each sync runs in a single transaction, partial updates do not occur. |

## Identification linkage checks

- Identification forms now treat the cleaned **Taxon (verbatim or free text)** as the authoritative entry. The system auto-links to a controlled **Taxon record** only when the cleaned text uniquely matches an accepted taxon; the linked record renders as read-only in the admin and user forms.
- If staff report incorrect links after a sync, verify whether the cleaned taxon text exactly matches multiple accepted taxa (for example, duplicates across ranks). Resolve the ambiguity by correcting the text or updating the taxonomy records, then resave the identification.
- To roll back to pre-linking behavior temporarily, deploy code that disables the auto-link helper and reverse migrations `0071` → `0070` → `0069` so the legacy `taxon` column becomes the primary source again. Reapply the migrations once the taxonomy data is corrected.

## Security considerations

Only grant `cms.can_sync` to trusted administrators. The sync process has write access to the taxonomy tables and can deactivate taxa when configured to do so.
