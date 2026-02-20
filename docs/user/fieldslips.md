# Field slip management

## Sedimentary fields and page placement

Field slip detail and edit workflows use the same sedimentary data contract:

- Sedimentary features
- Associated fossil groups
- Preservation states
- Recommended collection methods
- Collection position
- Matrix association
- Surface exposure
- Matrix grain size

For readability, the **Field slip detail** page displays this group in a dedicated sedimentary section before the **Related accessions** section.

In list views, these values are intended for filtering and search criteria. They are not intended to add extra columns to the field slip table.

## Editing and filtering sedimentary data

Collection managers and superusers can now maintain sedimentary data directly on the Field Slip create/edit form.

### What can be edited

- Sedimentary features
- Associated fossil groups
- Preservation states
- Recommended collection methods
- Collection position
- Matrix association
- Surface exposure
- Matrix grain size

### Where this appears

- **Field slip detail page:** sedimentary context appears in its own grouped section before **Related accessions**.
- **Field slip list page:** sedimentary values are exposed as filters in the search panel.
- **Field slip list table:** remains unchanged; sedimentary values are not shown as new columns.

### Filtering behavior

You can combine sedimentary filters with existing field slip filters (collector, date, locality, taxon, and horizon) to narrow records. Multi-select sedimentary filters return each matching field slip once, even when multiple related values match.

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
