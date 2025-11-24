# Taxonomy Sync (NOW Mammals)

This guide covers the administrative workflow for synchronising the CMS taxonomy with the NOW mammal dataset. The tooling lives inside the Django admin and provides a preview-first experience followed by a transactional apply step.

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

* Source (`NOW`)
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
| Sync result shows `ok = False` | Investigate the associated import log. Nothing was committed; fix the issues and run again. |
| Need to undo a sync | Locate the relevant `TaxonomyImport`, export the list of affected taxa, and restore them from backups or re-run the sync after correcting the upstream data. Because each sync runs in a single transaction, partial updates do not occur. |

## Identification linkage checks

- Identification forms now treat the cleaned **Taxon (verbatim or free text)** as the authoritative entry. The system auto-links to a controlled **Taxon record** only when the cleaned text uniquely matches an accepted taxon; the linked record renders as read-only in the admin and user forms.
- If staff report incorrect links after a sync, verify whether the cleaned taxon text exactly matches multiple accepted taxa (for example, duplicates across ranks). Resolve the ambiguity by correcting the text or updating the taxonomy records, then resave the identification.
- To roll back to pre-linking behavior temporarily, deploy code that disables the auto-link helper and reverse migrations `0071` → `0070` → `0069` so the legacy `taxon` column becomes the primary source again. Reapply the migrations once the taxonomy data is corrected.

## Security considerations

Only grant `cms.can_sync` to trusted administrators. The sync process has write access to the taxonomy tables and can deactivate taxa when configured to do so.
