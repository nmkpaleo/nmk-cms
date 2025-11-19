# FieldSlip Merge Deduplication QA & Rollout

_Last updated: 2025-11-13_

## Environment Preparation
1. Switch the project to SQLite for local verification:
   ```bash
   export DB_ENGINE=django.db.backends.sqlite3
   export DB_NAME="$(pwd)/db.sqlite3"
   ```
2. Apply migrations before running any tests:
   ```bash
   python app/manage.py migrate --noinput
   ```
   The command completes after replaying the historical `cms` migrations and allied Django apps on the SQLite database.

## Quality Checks
### Linting
- Running the full lint sweep uncovers legacy issues (unused imports, unused variables, and shadowed names) across modules unrelated to the FieldSlip merge scope. The job exits with 131 violations, so treat the report as informational until the broader cleanup occurs.
- The FieldSlip merge touchpoints (`cms.merge`, `cms.admin_merge`, and the regression tests) lint cleanly:
  ```bash
  python -m ruff check app/cms/merge app/cms/admin_merge.py app/cms/tests/test_fieldslip_merge.py
  ```
  `ruff` reports “All checks passed!” for the focused run.

### Django System Check
```bash
python app/manage.py check
```
The check passes with only the existing import-export warning surfaced; no new issues were introduced.

### Test Execution
- Attempting to run the entire pytest suite currently fails because `pytest-django` is not installed, so core fixtures such as `client` are unavailable and Django rejects `testserver` without an `ALLOWED_HOSTS` override.
- After exporting the SQLite overrides and migrating, the FieldSlip regression module executes successfully with merge-feature toggled on:
  ```bash
  ENABLE_ADMIN_MERGE=1 python -m pytest app/cms/tests/test_fieldslip_merge.py
  ```
  All four tests pass with the expected warnings only.

## Coverage Summary
Capture coverage for the focused suite using the standard-library `trace` module:
```bash
ENABLE_ADMIN_MERGE=1 python -m trace --count --summary \
  --ignore-dir=/root/.pyenv/versions/3.11.12/lib/python3.11 \
  --ignore-dir=/root/.pyenv/versions/3.11.12/lib/python3.11/site-packages \
  --coverdir=.trace-fieldslip \
  --module pytest app/cms/tests/test_fieldslip_merge.py
```
The summary reports 100% coverage for all merge-related modules exercised by the suite, confirming the deduplication paths are fully traced.

## Staging Validation Checklist
1. Enable the merge feature flag in the staging environment (`ENABLE_ADMIN_MERGE=1`).
2. Reproduce a merge with overlapping accession links; confirm the confirmation panel lists skipped and deleted relations alongside successes.
3. Review the corresponding `MergeLog` entry to verify the relation action counts align with the admin messages.
4. Trigger a dry-run merge to ensure the duplicate links remain untouched and the warning banner calls out the would-delete count.
5. Spot-check django-simple-history entries for the removed `AccessionFieldSlip` rows and confirm no unrelated history noise appears.

## Rollback Strategy
1. Revert the merge-deduplication service and admin wiring commits, then redeploy.
2. Disable the merge feature flag (`ENABLE_ADMIN_MERGE=0`) while the rollback propagates.
3. Restore any affected accession links from the most recent database backup if a merge was executed during the faulty window.
4. Clear Django messages in the admin interface to avoid stale deduplication summaries confusing staff.
