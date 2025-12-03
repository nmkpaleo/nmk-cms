# Merge admin flow analysis

## Objective
Map how selected IDs propagate through the admin merge flow and identify where the workflow stops after processing only two records.

## Changelist action → admin merge view
- The admin action `merge_selected` collects the checked row IDs and redirects to the merge view with a comma-separated `ids` query parameter. It validates a minimum of two selections before redirecting. (`MergeAdminMixin.merge_selected`)
- The merge view reads `ids` (or `selected_ids` on POST) via `_extract_selected_ids`, preserving the incoming order. (`MergeAdminMixin._extract_selected_ids`)

## Target and source preselection
- Initial form state pulls **target** from the first ID and **source** from the second ID when available: `selected_ids[0]` and `selected_ids[1]`. Any additional IDs are stored only in the hidden `selected_ids` field. (`MergeAdminMixin.merge_view` initial_source/initial_target)
- The rendered form and merge call accept only one `source` and one `target`; no iteration occurs over remaining IDs. (`MergeAdminMixin.merge_view`)

## Field-selection link
- When field selection is required, `_build_field_selection_url` includes the target ID plus the deduplicated `selected_ids` list as the `candidates` query parameter. (`MergeAdminMixin._build_field_selection_url`)
- The field-selection view can render multiple candidates, but it still expects a single target and infers the **source** as the first non-target candidate. (`FieldSelectionMergeView.get_candidates` and `_get_source_candidate`)

## Merge execution
- Submitting the admin form triggers exactly one merge call: `merge_records(source, target, strategy_map, user=request.user)`. Extra IDs in `selected_ids` are unused during execution. (`MergeAdminMixin.merge_view`)
- The field-selection POST path likewise merges one source into one target inside a transaction, ignoring any additional candidate IDs beyond the first source/target pair. (`FieldSelectionMergeView.post`)

## Key limitation
Because the admin view and field-selection flow each operate on a single `source`/`target` pair, selecting more than two records in the changelist only merges the first two; the remaining selections are neither iterated over nor queued for subsequent merges.
