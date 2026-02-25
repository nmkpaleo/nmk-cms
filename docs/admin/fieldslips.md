# FieldSlip admin and merge auditing


## Sedimentary data contract for field slips

Field slip sedimentary data is standardized across detail, edit, and filtering workflows. The canonical fields are:

- Sedimentary features
- Associated fossil groups
- Preservation states
- Recommended collection methods
- Collection position
- Matrix association
- Surface exposure
- Matrix grain size

Operational placement expectations:

- On detail pages, keep the sedimentary section before the Related accessions section to preserve a clear data-entry and review flow.
- On list pages, expose these fields as search criteria only; do not add them to the Field Slips results table columns.

The FieldSlip model participates in the same merge engine used across the CMS. Staff users with the **can_merge** permission can merge duplicates either in the admin or from an accession detail page. Both paths share merge logging, relation reconciliation, and history capture so administrators can audit and roll back changes.

## Sedimentary edit and filter operations

### Access expectations

- Field slip create/edit views continue to follow collection-manager access rules.
- Field slip list visibility and filtering are available to collection managers,
  curators, and superusers.

### Admin verification checklist

When validating a release that includes sedimentary updates:

1. Open an existing field slip and update one or more sedimentary fields.
2. Confirm the detail page shows the sedimentary block before **Related accessions**.
3. Open the field slip list and apply sedimentary filters, including at least one multi-select filter.
4. Verify results are deduplicated (no repeated rows for the same field slip) and that table columns are unchanged.

### Audit notes

- Field-level edits are captured by django-simple-history snapshots for FieldSlip records.
- Filtering does not mutate data and is intended for search and review workflows only.

## QC approval ingestion checks

When validating releases that include field-slip OCR/QC ingestion updates:

1. Run an intern + expert review cycle on a sample card that includes
   provenance and sedimentary checkboxes.
2. Approve the media and confirm the resulting FieldSlip stores:
   - collection/matrix/surface values,
   - sedimentary/fossil/preservation/recommended-method relations,
   - matrix grain size and accession link rows.
3. Re-approve the same reviewed payload in staging and confirm no duplicate
   `AccessionFieldSlip` links or duplicated relation rows are created.

## Permissions and entry points

- **Admin merge tool**: Available from the FieldSlip changelist when `MergeAdminMixin` is registered. Select duplicates, choose **Merge selected records**, and complete the compare screen.
- **Accession detail merge form**: Surface for authenticated users who hold the **can_merge** permission on FieldSlip. The form only lists slips already linked to the accession and redirects back to the accession page after completion.

## Audit trail

- Each merge runs inside a transaction and produces a `MergeLog` entry with snapshots of the target before merge and the deleted source. The log also records how duplicate `AccessionFieldSlip` rows were reconciled (skipped, deleted, or reassigned).
- django-simple-history captures a history row for the target and source slips, making it easy to inspect state before and after the merge directly from the admin history view.
- Success messages include relation summaries so staff can confirm how many accession links moved and whether any duplicates were removed.

## Rollback steps

1. Find the relevant `MergeLog` entry in the admin or via the shell. Download or copy the `source_snapshot` and `target_before_snapshot` payloads.
2. Recreate the deleted source FieldSlip using the snapshot data (admin form or import). Reapply the target snapshot to undo unwanted changes to the surviving slip.
3. Re-link accessions as needed. If a duplicate `AccessionFieldSlip` row was removed, add the restored slip back to the accession from the **Related field slips** panel.
4. Record the rollback in the log entry notes or a new admin comment to keep the audit trail complete.

## Operational reminders

- Always perform merges and rollbacks with the feature flag and permissions intact; disabling the merge tool removes the admin action but does not affect existing logs.
- For large correction batches, capture a database backup before executing merges so you can restore quickly if an audit reveals widespread issues.
