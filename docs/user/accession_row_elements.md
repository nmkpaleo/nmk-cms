# Accession Row Elements: Merge and Delete

Collection managers can manage duplicate or erroneous specimen elements directly from an accession row detail page.

## Merge duplicate elements

1. Open the accession row detail page.
2. Select **Merge element**. The panel opens with all elements linked to the row.
3. Choose one **Target** and at least one **Source** checkbox, then click **Continue**.
4. Review the confirmation screen and pick the preferred values for each field (element name, side, condition, description, portion, fragments).
5. Submit to merge. All selected sources are merged into the target sequentially, preserving audit history.

### Rules and safeguards

- Only elements on the same accession row can be merged.
- The merge tool requires the staff merge permission and the merge feature flag to be enabled.
- If validation fails, error messages appear and the panel stays open so you can adjust the selection.

## Delete an element

1. From the elements table, choose **Delete** (when available).
2. Confirm the deletion to remove the element from the accession row.

### Deletion notes

- Deletion is permission-gated; only authorized staff see the action.
- Deletions honor the same merge feature flag and record history for audit where enabled.

## Troubleshooting

- If the merge panel does not stay open, add `?merge_elements=open` to the accession row URL and reload.
- Ensure a target plus at least one source are selected before continuing; otherwise, the form will show an error and no merge will occur.
- If the confirmation step does not appear, confirm that the target was included in the submitted selection and that the merge feature flag is enabled.
