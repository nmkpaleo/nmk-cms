# FieldSlip Merge Workflow Analysis

## Overview
- `FieldSlip` inherits the shared `MergeMixin`, exposing merge actions in the admin via `FieldSlipAdmin`, which stacks `MergeAdminActionMixin` and `MergeAdminMixin` so staff can trigger merges when the `MERGE_TOOL_FEATURE` toggle is enabled.【F:app/cms/models.py†L626-L660】【F:app/cms/admin.py†L249-L358】【F:app/cms/admin.py†L668-L674】
- The merge engine used by the admin combines field-level strategies with relation directives resolved inside `merge_records`, executing within a single transaction for both data updates and merge logging.【F:app/cms/merge/engine.py†L431-L578】

## Model Relationships Involved
- Accessions link to field slips through the explicit join model `AccessionFieldSlip`, whose `unique_together` constraint prevents duplicate `(accession_id, fieldslip_id)` rows.【F:app/cms/models.py†L768-L799】
- On the `FieldSlip` side, the reverse relation exposes `accession_links`, which the merge engine treats as a foreign key relation requiring reassignment when two slips are merged.【F:app/cms/models.py†L768-L783】【F:app/cms/merge/engine.py†L139-L192】

## Current Relation Handling During Merge
- For every auto-created relation discovered on the source slip, `_normalise_relation_spec` falls back to the default directive when no custom rule exists. For FK/one-to-one relations that default action is `reassign`, implemented by `_reassign_related_objects`.【F:app/cms/merge/engine.py†L73-L192】【F:app/cms/merge/mixins.py†L12-L47】
- `_reassign_related_objects` performs a `select_for_update()` on the related manager tied to the source slip and issues a bulk `UPDATE` that points each relation at the merge target. No collision detection occurs before the update, so any pre-existing link on the target with the same `(accession_id, fieldslip_id)` raises the MySQL integrity error seen in production.【F:app/cms/merge/engine.py†L139-L192】【F:app/cms/models.py†L792-L796】
- Many-to-many relations, by contrast, go through `_merge_many_to_many`, which explicitly checks for existing rows on the through model before moving them, skipping duplicates safely. That protective logic is absent for FK reassignment, highlighting the behavioral gap for `AccessionFieldSlip` relations.【F:app/cms/merge/engine.py†L195-L259】

## Identified Insertion Points for Deduplication
1. **Custom relation directive for `accession_links`:** register a relation strategy on `FieldSlip` that routes to a bespoke callback capable of de-duplicating `AccessionFieldSlip` rows prior to reassignment, similar to the through-model guard used for many-to-many merges.【F:app/cms/merge/mixins.py†L12-L47】【F:app/cms/merge/engine.py†L195-L259】
2. **Enhance `_reassign_related_objects`:** introduce an optional opt-in path (e.g., via directive options) that filters out rows where the target already has a matching relation, falling back to delete-or-skip semantics instead of bulk updating everything blindly.【F:app/cms/merge/engine.py†L139-L192】
3. **Pre-merge reconciliation in the admin workflow:** before invoking `merge_records`, the admin mixin could inspect `AccessionFieldSlip` memberships for the chosen source and target and surface conflicts to the user, allowing them to prune duplicates or proceed with a safe merge strategy that ignores already linked accessions.【F:app/cms/admin_merge.py†L214-L347】

Each option keeps schema changes out of scope while providing a clear location to integrate duplicate handling logic for the FieldSlip merge path.
