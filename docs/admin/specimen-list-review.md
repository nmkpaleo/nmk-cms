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
