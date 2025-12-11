# Element merge quickstart

Use this guide when you need to consolidate duplicate Elements with the field-selection merge flow.

## Permissions and feature gates
- Sign in as a staff user who has the **can_merge** permission on Elements.
- Ensure the merge tool is enabled (feature flag `ENABLE_ADMIN_MERGE` and the Element merge registry entry). Without both, merge links redirect back to the changelist.

## Running a merge
1. From the Element admin changelist, select two or more Elements that represent the same concept and pick **Merge selected records**.
2. Choose the target and source on the compare screen. When both are set, follow **Open field selection merge** to reach the per-field view with all selected candidates preloaded.
3. For each field row, pick the correct value:
   - **Name**: pick the canonical label to keep.
   - **Parent**: choose carefully to avoid cycles; leave the target parent selected unless you intentionally reparent.
4. Submit to merge. You will be redirected to the target Element change page with a success banner once all sources are merged.

## Rollback and safety
- Field selection prevents accidental overwrites by requiring an explicit choice for sensitive fields; validation blocks self-merges and parent cycles.
- The merge engine records a `MergeLog` entry and a django-simple-history revision for the target. If you need to undo changes, revert to the prior history version for the Element.
- For testing or cautious reviews, run a dry merge in development using the `dry_run` flag (no database writes or logs) before executing in production.
