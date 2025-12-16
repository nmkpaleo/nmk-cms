# Merge Tool

The merge tool lets authorised staff review duplicate records side-by-side and consolidate them into a single canonical entry. It relies on the `MergeAdminMixin` and merge engine that power automated logging and relation handling.

The interface now renders entirely with W3.CSS containers and cards, so the admin changelist action, compare screen, and candidate search share consistent spacing without relying on bespoke stylesheets. Expect each step to appear inside a `w3-card-4` wrapper with W3 tables for comparison rows; any spacing tweaks should continue to use W3 utilities instead of adding new CSS rules.【F:app/cms/templates/admin/cms/merge/merge_form.html†L1-L174】

## Prerequisites and Access Control

1. Ensure the model is registered with the Django admin using `MergeAdminMixin` so the merge workflow, templates, and actions are available.
2. Grant the **`can_merge`** permission for the model to the groups or users that should initiate merges. Users without the permission will not see the action and will be redirected back to the changelist if they attempt to access merge URLs.
3. Users must be marked as staff members to access the admin and the merge candidate search endpoint.

## Accessing the merge tools

- **Admin merge form** – open any merge-enabled model's changelist, select the duplicate rows, and choose **Merge selected records** from the actions menu. This launches the compare-and-confirm screen at `.../admin/<app>/<model>/<id>/merge/` and keeps **all** selected IDs in the request so downstream steps can process them.
- **Fuzzy candidate search** – visit `/merge/` while logged in as a staff user to open the dedicated search UI. The form lists every model registered with `MERGE_REGISTRY` and sends requests to `/merge/search/` to return scored candidates.
- Both entry points honour the `MERGE_TOOL_FEATURE` flag: when disabled the URLs remain hidden and the templates render a clear *feature disabled* notice.

### Per-field selection workflow

- When a model defaults to the `FIELD_SELECTION` strategy for a field, the compare screen surfaces a yellow banner with an **Open field selection merge** link once a target and source are chosen.
- Elements use this workflow for `name` and `parent_element`; pick a parent intentionally to avoid introducing hierarchy cycles during the merge.
- Follow the link to load the dedicated field-selection view at `/merge/field-selection/` with the `model`, `target`, and **all candidates** query parameters prefilled. The view is staff-only and respects the same feature flag.
- Pick the value to keep for each field using the radio buttons across the source and target columns. Leave fields untouched to keep the target value. The view preserves the target you selected on the admin form and will merge **every remaining source** into that target sequentially using the same strategy map.
- Submit to complete the merge; the view redirects back to the target’s admin change page with a success banner that aggregates the relation/field updates across all merged sources and records the full sequence in `MergeLog`.

## Feature Flag Rollout and Safeguards

The merge tooling is disabled by default and is controlled through the `ENABLE_ADMIN_MERGE` environment variable (surfaceable as `settings.MERGE_TOOL_FEATURE`).

### Enabling the tool

1. **Back up the production database** before rollout. For MySQL deployments:

   ```bash
   mysqldump -u "$DB_USER" -h "$DB_HOST" -p"$DB_PASS" "$DB_NAME" \
     > backups/"$(date +%Y%m%d-%H%M)"-pre-merge-tool.sql
   ```

   For SQLite (e.g. local development):

   ```bash
   python app/manage.py dbshell ".backup 'backups/$(date +%Y%m%d-%H%M)-pre-merge-tool.sqlite'"
   ```

2. Export the feature flag as part of your deployment environment: `ENABLE_ADMIN_MERGE=1`.
3. Deploy the release and run `python app/manage.py migrate` to ensure the merge logging tables are present.
4. Verify the merge UI appears by visiting the admin changelist for a merge-enabled model and ensuring the **Merge selected records** action is available.

### Disabling the tool

1. Set `ENABLE_ADMIN_MERGE=0` (or remove the variable) in your deployment environment.
2. Redeploy the application; the merge actions, admin view, candidate search endpoint, and registry registration will be suppressed automatically.
3. Confirm the templates now display a *feature disabled* message and that merge actions are absent from the admin action menu.

## Monitoring Merge Failures

The admin workflow emits a `cms.merge.signals.merge_failed` signal and records a structured log message whenever a merge attempt raises an exception. If Sentry is installed, a breadcrumb and captured exception are also sent automatically. Connect additional listeners to the signal in your project’s `apps.py` or a dedicated monitoring module to integrate with paging/alerting systems:

```python
from django.dispatch import receiver
from cms.merge.signals import merge_failed


@receiver(merge_failed)
def alert_on_merge_failure(sender, **payload):
    error = payload["error"]
    source = payload.get("source")
    target = payload.get("target")
    # Send to PagerDuty, Slack, etc.
    notify_ops(
        f"Merge failed for {source} → {target}: {error}",
    )
```

## Rollback Guidance

If a merge needs to be reversed after the fact:

1. Locate the relevant `MergeLog` entry (via the admin or shell) and download the archived snapshots contained in `source_snapshot` and `target_before_snapshot`.
2. Restore the source record from the archived snapshot—create a new instance using the serialised fields or re-import the JSON through a management command.
3. Reapply the `target_before_snapshot` data to undo unwanted changes to the target record.
4. Update or delete the `MergeLog` entry to reflect the rollback and retain an auditable trail.
5. If widespread issues are detected, disable the feature flag and restore the database backup captured prior to rollout.

## Launching the Merge Workflow

1. Navigate to the model’s changelist in the admin.
2. Select at least two records that represent duplicates; more are allowed, and the admin will keep all IDs in order.
3. Choose **Merge selected records** from the actions drop-down and submit the form.
4. Review the merge form. The target record appears on the left and the first source on the right. Adjust the **Strategy** column for each field if necessary and provide manual values when prompted by the *User Prompt* strategy. Additional candidates appear in a stacked list beneath the current selection.
5. Submit the form to execute the merge. The system loops through every listed source and merges it into the chosen target sequentially using the same strategies. A success message confirms the source data moved into the target and includes the number of fields updated across all merges.

Behind the scenes the merge engine reassigns relations, archives the source snapshot, deletes the source record, and records the result in `MergeLog`. Refer to `app/cms/tests/test_admin_merge.py` and `app/cms/tests/test_merge_engine.py` for concrete examples of the full workflow.

### FieldSlip accession-link reconciliation

When merging FieldSlips the admin will now see an additional info panel describing the automatic reconciliation of duplicate accession links. The merge engine analyses the `AccessionFieldSlip` join table inside the same transaction as the merge, deleting conflicting rows before reassigning the remaining links to the target slip. The confirmation screen surfaces how many duplicates were skipped or deleted so staff do not need to manually clean up accessions before finalising the merge.

Key takeaways for staff users:

- No IntegrityError will block the merge when both FieldSlips already reference the same accession; the duplicate link is removed automatically.
- Relation summaries appear alongside the standard merge success banner, making it easier to audit which accessions moved, were skipped, or were deleted.
- The audit trail in `MergeLog` captures these relation actions so administrators can review the conflict handling at any time.

### Accession Reference field-selection merges

- Accession Reference merges are limited to records that belong to the **same accession**; cross-accession merges are blocked before any data changes.
- The field-selection view is mandatory and surfaces the **Reference** and **Page** fields for every candidate. Choose one value per field; leave a field unselected to keep the target’s value.
- The compare screen links to the field-selection page once both a target and source are chosen. The link preserves all selected candidates so the merge can process them sequentially into the target.
- Successful merges redirect back to the target change page with a banner summarising the updates. Merge logs and django-simple-history entries capture the before/after state for rollback.

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
