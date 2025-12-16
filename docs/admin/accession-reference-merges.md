# Accession Reference Merges (Admin)

Use the merge tool to consolidate duplicate accession references that point to the **same accession**. The admin workflow relies on the per-field selection view so staff can choose which values to keep.

## Access and prerequisites

- Sign in as staff with the **change Accession Reference** permission; the merge action is hidden otherwise.
- The merge feature must be enabled via the deployment flag. When disabled, merge actions and field-selection views stay hidden.
- All candidates must belong to the same accession. Cross-accession merges are blocked before any data changes occur.

## Launching a merge

1. Open **Accession references** in the Django admin.
2. Select at least two rows for the same accession and choose **Merge selected records**.
3. Pick a target and source on the compare screen. A yellow notice links to the field-selection page once both roles are set.
4. Follow the **Open field selection merge** link to choose the values to keep.

## Choosing field values

- The field-selection page lists the **Reference** and **Page** fields for every candidate. Pick one value per row; leave a field unselected to keep the target’s value.
- Submitting applies the chosen values to the target and merges every source into it sequentially.
- On success you return to the target change page with a banner summarising the merge. A merge log and history records capture the updates for audit and rollback.

## Rollback reminders

- Each merge creates history entries for the target and a merge log snapshot. Use these records to reconstruct the source if a merge needs to be undone.
- If issues span multiple merges, disable the merge feature flag and restore the pre-merge database backup.
