# Merge Tool

The merge tool lets authorised staff review duplicate records side-by-side and consolidate them into a single canonical entry. It relies on the `MergeAdminMixin` and merge engine that power automated logging and relation handling.

## Prerequisites and Access Control

1. Ensure the model is registered with the Django admin using `MergeAdminMixin` so the merge workflow, templates, and actions are available.
2. Grant the **`can_merge`** permission for the model to the groups or users that should initiate merges. Users without the permission will not see the action and will be redirected back to the changelist if they attempt to access merge URLs.
3. Users must be marked as staff members to access the admin and the merge candidate search endpoint.

## Launching the Merge Workflow

1. Navigate to the model’s changelist in the admin.
2. Select at least two records that represent duplicates.
3. Choose **Merge selected records** from the actions drop-down and submit the form.
4. Review the merge form. The target record appears on the left and the source on the right. Adjust the **Strategy** column for each field if necessary and provide manual values when prompted by the *User Prompt* strategy.
5. Submit the form to execute the merge. A success message confirms the source data moved into the target and includes the number of fields updated.

Behind the scenes the merge engine reassigns relations, archives the source snapshot, deletes the source record, and records the result in `MergeLog`. Refer to `app/cms/tests/test_admin_merge.py` and `app/cms/tests/test_merge_engine.py` for concrete examples of the full workflow.

## Configuring Strategies

Merge strategies determine how conflicting field values resolve:

- **Last Write Wins** – Always favour the source value.
- **Prefer Non Null** – Keep the first non-empty value (source first by default).
- **Concatenate Text** – Combine string content with a delimiter.
- **User Prompt / Custom** – Require a manual value or callback.

You can set default strategies on the model via the `merge_fields` mapping or override them per merge through the form. Relation handling follows the `relation_strategies` map defined on `MergeMixin` subclasses.

For more dynamic configuration register defaults in code:

```python
from cms.merge.constants import MergeStrategy
from cms.merge.registry import register_merge_rules

register_merge_rules(
    MyModel,
    fields={
        "display_name": MergeStrategy.LAST_WRITE,
        "email": MergeStrategy.PREFER_NON_NULL,
    },
    relations={
        "memberships": "merge",
    },
)
```

This pattern ensures the admin form and background merges use consistent defaults. See the tests mentioned above for additional registry usage examples.

## Fuzzy Candidate Search

The **Find merge candidates** screen provides a fuzzy search powered by the same registry. Pick a registered model, supply a query, and optionally adjust the similarity threshold. Results include the similarity score and preview fields so you can quickly assess potential duplicates.

## Troubleshooting

- **Action missing** – Confirm the user has the `can_merge` permission and that the model admin inherits from `MergeAdminMixin`.
- **Forbidden JSON response** – The candidate search endpoint requires authenticated staff users; log in via the admin first.
- **Unexpected strategy outcomes** – Review the strategy log stored on the matching `MergeLog` entry and cross-reference automated coverage in `app/cms/tests/test_merge_engine.py`.
