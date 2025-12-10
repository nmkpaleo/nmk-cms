# FieldSlip admin and merge auditing

The FieldSlip model participates in the same merge engine used across the CMS. Staff users with the **can_merge** permission can merge duplicates either in the admin or from an accession detail page. Both paths share merge logging, relation reconciliation, and history capture so administrators can audit and roll back changes.

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
