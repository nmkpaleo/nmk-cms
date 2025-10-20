# Taxonomy Management

The collection taxonomy is synchronised with the NOW (New and Old World) mammal dataset so that accepted names and synonyms stay up to date. The sync workflow is exposed to collection managers through the Django admin and is designed to keep Identification records pointing at accepted taxa only.

## Who can run a sync?

* You must be a staff user with the **`cms.can_sync`** permission.
* Ask an administrator to grant access if the **Sync Taxa Now** button does not appear on the Taxon admin page.

## Before you start

1. Confirm that the NOW dataset URLs are reachable from your network. If the preview reports connection errors, wait and try again or contact IT to verify the environment variables:
   * `TAXON_NOW_ACCEPTED_URL`
   * `TAXON_NOW_SYNONYMS_URL`
2. Set aside time to review the preview carefully—large imports may take up to a minute to generate.
3. Ensure no one else is running a sync at the same time to avoid confusion.

## Previewing the changes (dry-run)

1. Sign in to the Django admin and open **CMS → Taxa**.
2. Click **Sync Taxa Now** in the toolbar. The system fetches the latest accepted and synonym TSV files and computes a preview.
3. Review the summary cards and each section. They show what will be created, updated, deactivated, or flagged as an issue.
4. If issues are listed, download the preview (or take screenshots) and resolve the problems before applying the sync. Common issues include synonyms referencing missing accepted taxa.

Previewing does not change the database—it is a safe dry-run.

## Applying the sync

1. From the preview screen, press **Apply sync**.
2. Wait for the confirmation screen. The process runs inside a single transaction; if anything fails the database is rolled back automatically.
3. Review the results. If the run succeeded you will see a green success banner and a link to the Import Log entry.
4. Return to the taxonomy changelist to continue working, or click **Run preview again** to refresh the summary.

## After the sync

* Use the **View import log** link to inspect counts, recorded issues, and the NOW source version that was applied.
* Accepted taxa and synonyms remain active; any records missing from the source may be deactivated when `TAXON_SYNC_DEACTIVATE_MISSING` is enabled.
* Identifications continue to point at accepted taxa. If a specimen still references an inactive or synonym record, contact the digitisation team to clean up the data.

## Troubleshooting

| Symptom | Suggested action |
| --- | --- |
| Network error fetching TSV files | Confirm the NOW repository is reachable and the URLs are configured correctly. Retry once connectivity is restored. |
| Issues flagged in preview | Review the issue context, fix the underlying data (for example, add the accepted taxon to NOW), then rerun the preview. |
| Import log shows `ok = false` | Inspect the logged issues, correct them, and re-run the sync. Nothing is applied when the transaction fails. |
| Button missing | Verify that you are a staff user with the `cms.can_sync` permission. |

Contact the technical team if a problem persists or if you need to restore from a previous import log.
