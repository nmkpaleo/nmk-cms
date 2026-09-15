# Specimen List Review

## Side/Portion fallback behavior

When staff approve a specimen-list page row with an element value like `Lt femur prox`, the review pipeline can fill missing **Side** and **Portion** values automatically.

- Side token examples: `Lt`, `Left`, `Rt`, `Right`
- Portion token examples: `Dist`, `Distal`, `Prox`, `Proximal`
- Stored canonical values: `left` / `right`, `distal` / `proximal`

If a reviewer already supplied Side or Portion explicitly, that value is preserved.

## Admin and audit expectations

- Nature of Specimen changelist pages continue to render rows containing inferred values.
- The history log records the final persisted Side and Portion values.
- Existing specimen-list queue filters remain usable after approvals that rely on fallback inference.

## Media location synchronization operations

During page approval, related media locations are synchronized to the approved page-image path.

### What admins should verify
- Approval completed without error in the review queue.
- Media records linked to the approval show updated file locations.
- History entries show the acting reviewer when available.

### Rollback and recovery
- If approval sync fails, the workflow stops and shows an error so staff can retry after the issue is resolved.
- For legacy or partial mismatches, run the reconciliation command in dry-run mode first, then apply with an actor username.
- Execute reconciliation in batches (`--limit`) for large datasets and confirm results between runs.

See the development runbook for command examples and staged rollout guidance.
