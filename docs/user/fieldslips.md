# Field slip management

## Merging field slips from an accession

Staff users with the **can_merge** permission on field slips can now merge duplicates directly from an accession detail page. This flow keeps you on the accession and automatically refreshes the linked slips after the merge finishes.

1. Open the accession detail page and scroll to the **Related field slips** panel.
2. In the **Merge field slips** form, choose the **Target field slip** you want to keep and the **Source field slip** you want to merge into it. Only slips already linked to the accession appear in the dropdowns.
3. Submit the form. On success, the page redirects back to the accession detail view with an updated list and a confirmation banner. If either slip is not linked or the same record is selected twice, the form shows an error and no changes are applied.

Use the existing "Link existing field slip" and "Create and link new field slip" options in the same panel to manage links without merging.

### Audit trail and rollback expectations

- Every merge records a history row for the target and source field slips via django-simple-history, and the merge engine captures a structured `MergeLog` entry describing how accession links were deduplicated.
- The accession detail page will always redirect back after a merge, so you can immediately review the updated list and its history links.
- To undo a merge, locate the associated `MergeLog` entry and corresponding history version. Recreate the deleted source from the archived snapshot, reapply the pre-merge target state if necessary, and re-link the restored slip to the accession.
- If the merge removed a duplicate `AccessionFieldSlip` link, simply re-add the slip from the **Related field slips** panel after restoration.
