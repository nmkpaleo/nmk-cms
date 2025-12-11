# Element merges in the Django admin

Element records now participate in the admin merge workflow using the standard **Merge selected records** action exposed on the Element changelist. Staff users need the `can_merge` permission and the `MERGE_TOOL_FEATURE` flag enabled to see the action; without either prerequisite the merge URLs redirect back to the changelist.

- **Field selection** – Element defaults to the FIELD_SELECTION strategy for `name` and `parent_element`, so the admin form links to the dedicated field-selection UI. Use the field-selection page to pick the parent intentionally and avoid hierarchy cycles before the merge executes.【F:app/cms/admin.py†L797-L802】【F:app/cms/tests/test_element_admin_merge.py†L120-L139】
- **History and audit** – Each merge records an entry in `MergeLog` and creates a django-simple-history revision for the target Element. The latest history entry reflects the merge user and makes it easy to audit what changed.【F:app/cms/merge/engine.py†L547-L582】【F:app/cms/tests/test_element_admin_merge.py†L140-L159】
- **Fallback to merge docs** – For broader merge tooling guidance, including candidate search and troubleshooting, see `docs/admin/merge-tool.md`.

When testing locally, select at least two Element rows from the changelist, run the action, and follow the field-selection link. On submission you should land back on the target Element’s change page with a success banner summarising field updates and relation moves.

## Rollback and QA notes
- **Dry runs in dev**: Set `dry_run=True` when calling `merge_elements` in a shell to verify selections without saving or creating `MergeLog` rows.【F:app/cms/merge/services.py†L11-L36】【F:app/cms/merge/engine.py†L700-L739】 The admin UI always executes real merges, so use dev/staging when testing risky hierarchy changes.
- **Reverting changes**: Each successful merge creates a django-simple-history revision and persists the resolved field map in `MergeLog`. To undo an incorrect merge, restore the previous history entry for the target Element via the admin history view; the log provides the exact values and relations that were applied.【F:app/cms/merge/engine.py†L700-L739】【F:app/cms/tests/test_element_admin_merge.py†L140-L170】
- **Validation coverage**: Element merges block self-merges and parent cycles, keeping the hierarchy safe even if staff select conflicting inputs. Permission gates and feature flags remain enforced on all merge URLs and actions.【F:app/cms/merge/element.py†L12-L33】【F:app/cms/tests/test_element_admin_merge.py†L63-L139】
