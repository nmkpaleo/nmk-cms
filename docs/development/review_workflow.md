# Review workflow (development)

Implementation and rollout notes for the specimen list review workflow.

## Feature flag
- `FEATURE_REVIEW_UI_ENABLED` is the top-level gate for review UI endpoints.
- Keep default enabled in local/dev, and gate production rollout through environment configuration.

## CI checks
Recommended CI commands for this workflow:

```bash
python app/manage.py makemigrations --check --dry-run
pytest tests/cms/test_review_workflow.py --cov=tests/cms/test_review_workflow.py --cov-fail-under=90
pytest app/cms/tests/test_specimen_list_review_approval.py
```

## Test scope
`tests/cms/test_review_workflow.py` covers:
- feature-flag gating for the queue
- review page navigation affordances (Back to queue)

`app/cms/tests/test_specimen_list_review_approval.py` covers approval transformations including taxon qualifier parsing.

## Rollout sequence
1. Deploy with flag off in production.
2. Run migrations.
3. Turn flag on for pilot users.
4. Monitor queue usage, approvals, and error logs.
5. Expand access after validation.
