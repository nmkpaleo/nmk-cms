# FieldSlip Merge Deduplication Notes

## Context
FieldSlip records participate in the merge framework through `MergeMixin`, exposing the merge action in the admin when the `MERGE_TOOL_FEATURE` flag is enabled. The merge engine operates in a single database transaction, reconciling field strategies and relation directives before logging to `MergeLog`.

Historically, merging FieldSlips that referenced the same accession raised a MySQL `IntegrityError` because the `AccessionFieldSlip` join model enforces a unique `(accession_id, fieldslip_id)` constraint. The reassignment step attempted to update every related row blindly, colliding with the existing link on the target slip.

## Implemented safeguards
- `FieldSlip.relation_strategies` opts the `accession_links` relation into the enhanced foreign-key reassignment flow by setting `deduplicate=True`.【F:app/cms/models.py†L642-L657】
- `_reassign_related_objects` now inspects unique constraints that involve the relation being reassigned. When `deduplicate` (or `skip_conflicts`) is enabled it loads the related rows with `select_for_update()` and builds targeted lookups to detect conflicts on the merge target before issuing updates. Conflicting rows are skipped, optionally deleted, and reported back through the merge result payload.【F:app/cms/merge/engine.py†L240-L307】
- Relation actions logged in `MergeResult.relation_actions` surface the `updated`, `skipped`, and `deleted` counts so admin views can display a concise summary after the merge completes.【F:app/cms/merge/engine.py†L590-L707】

## Admin workflow impact
The FieldSlip merge confirmation template now renders an informational panel describing the automatic accession reconciliation. After the merge the admin success banner includes the relation summary, ensuring operators can review how many accession links moved or were removed without inspecting the database directly.【F:app/cms/templates/admin/cms/merge/merge_form.html†L80-L150】【F:app/cms/admin_merge.py†L250-L347】

## Developer guidance
- **Dry-run support** – When the merge engine is invoked with `dry_run=True`, duplicate rows are not deleted. Instead, `would_delete` counts are emitted so UIs and tests can present non-destructive previews.【F:app/cms/merge/engine.py†L240-L307】
- **Extending to other models** – Add a relation strategy with `deduplicate=True` (and optional `unique_fields` if the constraint spans additional attributes) to enable the same behaviour. The reassignment helper automatically inspects declared unique constraints but can be guided with explicit combinations when needed.
- **Regression coverage** – `app/cms/tests/test_fieldslip_merge.py` contains transactional tests that exercise duplicate accession scenarios, history logging, and dry-run previews. Use these tests as templates when introducing similar deduplication rules for other models.【F:app/cms/tests/test_fieldslip_merge.py†L1-L260】

## Operational considerations
- The deduplication routine relies on database-level locking to avoid race conditions. Keep merge operations quick and avoid long-running tasks inside the transaction.
- Because conflicting rows are deleted, ensure production backups remain in place to restore accidentally removed links if required. Merge logs include the source snapshot for auditing and potential rollback.

## Next Steps

- Refer to `docs/dev/fieldslip_merge_rollout.md` for the executed QA commands, coverage summary, and rollout guidance.
