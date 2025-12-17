# Merge Tool and Field Selection

The merge tool consolidates duplicate records into a single entry and now supports a per-field selection flow for models that require explicit choices. Use this guide to start merges from the admin and pick the exact values to keep.

## Who can merge

- Staff users with the **can_merge** permission on the model can launch the merge tool.
- The feature depends on the `ENABLE_ADMIN_MERGE` flag. When disabled, merge links and the field selection screen remain hidden.

## Starting a merge

1. Open the admin changelist for the model you want to merge (Field Slip, Storage, Reference, or Accession Reference).
2. Select **two or more** records that represent duplicates.
3. Choose **Merge selected records** from the actions menu and continue. The compare screen lists every selected record and shows the current **target** on the left with the first **source** on the right.
4. Pick the target and source in the **Current selection** cards. Extra candidates stay listed beneath and will be merged into the chosen target one after another in the order shown. When the model supports per-field choices, a yellow notice appears with an **Open field selection merge** link that carries all selected IDs.

## Using the field selection screen

- Follow the **Open field selection merge** link to load the per-field view with the target and source preselected **plus any additional candidates**. You must stay signed in as staff to access it.
- Each row lists a field, and each column shows the value from the target or any source with a radio button. Choose exactly one value per field; leave untouched fields unselected to keep the target value.
- Use the **Cancel** link to return to the previous page without changing data.
- Submit the form to merge. Every source is merged into the target sequentially using your chosen values, and you will be redirected back to the target’s admin change page with a success banner once all merges complete.

## Models using field selection by default

- **Field Slip:** key attributes such as citation or accession-related fields require explicit picks to avoid accidental overwrites.
- **Storage:** area values use field selection so curators can confirm the correct location during a merge.
- **Reference:** title and citation rely on field selection to preserve the authoritative record.
- **Element:** name and parent hierarchy require explicit choices to avoid cycles; keep the target’s parent unless you intentionally reparent during the merge.
- **Accession Reference:** reference text and page values require explicit choices and only merge when every candidate belongs to the same accession.

### Accession detail shortcut for accession references

- Collection managers can merge duplicate accession references from the accession detail page without visiting the admin. Open an accession, expand **Merge references**, select at least two linked references plus a target, and continue to the field-selection step to choose the reference and page values to keep. The flow reuses the same merge engine and audit trail as the admin action.

## Tips and troubleshooting

- If you see a 503 or 403 response, confirm the merge feature flag is enabled and that you are logged in with staff permissions.
- The merge logs still record history for every field, including those chosen through the selection screen, so audit trails remain complete.
- If the field selection link is missing, ensure a target and source are set on the merge form; the link appears only when both roles are filled.
