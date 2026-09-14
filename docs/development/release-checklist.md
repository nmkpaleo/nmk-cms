# Release checklist (`main` -> `prod`)

This project ships production releases by merging a pull request from `main` into `prod`.

## Versioning model

- Use Semantic Versioning tags: `vMAJOR.MINOR.PATCH` (for example `v1.4.2`).
- The workflow `.github/workflows/release-on-prod-merge.yml` creates the next tag automatically after a PR is merged into `prod`.
- Bump level comes from PR labels:
  - `release:major` -> major bump
  - `release:minor` -> minor bump
  - no release label -> patch bump

## Pre-merge checklist

1. Create PR from `main` to `prod`.
2. Confirm the branch contains only the intended, already-reviewed `main`
   changes and is synchronized with its base.
3. Confirm required CI and CodeQL checks are green.
4. Obtain an independent approval and resolve every review conversation.
5. Add one release label (`release:major` or `release:minor`) when needed.
6. Review `CHANGELOG.md`, migrations, deployment steps, and rollback impact.
7. Merge through the normal pull-request path without administrator bypass.

## Pagination filter persistence rollout notes

Use this checklist when releasing list pagination changes that must preserve active filter query parameters.

### Rollout
1. Validate Accessions and Localities filtered lists in staging.
2. Confirm **Previous/Next** links keep active filter parameters, including repeated values from multi-select fields.
3. Ask support users to smoke-test common filtered queues after deployment.

### Rollback
1. Revert the shared pagination template change in the release branch.
2. Redeploy and re-run smoke tests for Accessions and Localities lists.
3. Notify support teams that pagination has temporarily returned to previous behavior while a fix is prepared.


## FieldSlip sedimentary release readiness (FS-SED-008)

Use this checklist for releases that include FieldSlip sedimentary editing/filtering/detail updates.

### CI readiness

Confirm the following checks are green on both staging and production pipelines:

1. Django system checks (`python manage.py check`).
2. Migration drift checks (`python manage.py makemigrations --check --dry-run`).
3. Pytest with the repository coverage threshold (`--cov-fail-under=70`).
4. Documentation verification (`pytest tests/docs`).

### Staging walkthrough

Complete this walkthrough with a collection manager account before production merge:

1. Open a Field Slip detail page and confirm **Sedimentary context** appears before **Related accessions**.
2. Edit a Field Slip and save sedimentary values for all supported field types:
   - multi-select relations
   - choice fields
   - boolean surface exposure
   - matrix grain size reference
3. Re-open the same Field Slip and confirm saved values render correctly.
4. Open `/fieldslips/`, apply at least one multi-select sedimentary filter plus one non-sedimentary filter, and verify:
   - expected result row is returned
   - duplicate rows are not shown
   - list table columns remain unchanged
5. Run targeted regression coverage in staging CI logs:
   - `tests/cms/test_fieldslip_sedimentary_regressions.py`

### Rollback checklist

If release validation fails after deployment:

1. Revert the FieldSlip sedimentary feature commits in the release branch.
2. Redeploy and run `python manage.py check` plus smoke tests for Field Slip detail/edit/list pages.
3. Re-run migration check (`makemigrations --check --dry-run`) to confirm no schema drift.
4. Confirm list filters no longer expose problematic sedimentary criteria (if rollback removes them).
5. Notify operations/support teams and record rollback rationale in release notes.

## What happens after merge

1. `release-on-prod-merge` computes the next `v*` tag.
2. The workflow pushes the tag and creates a GitHub Release with generated notes.
3. `production-ci` runs on `prod` and on `v*` tags.
4. Docker image build gets `APP_VERSION` from the git reference (`v*` tag on release builds).

Check both workflow runs after the merge. A GitHub Release is not proof that the
container build or deployment succeeded.

## General rollback

1. Stop further promotion or automatic image updates.
2. Identify the last known-good release tag and image digest.
3. Revert the release change through a reviewed pull request, or redeploy the
   last known-good immutable image when application rollback is urgent.
4. Handle database migrations according to their documented reversibility; do
   not reverse a destructive migration without a verified backup.
5. Run system checks and focused smoke tests after rollback.
6. Record the affected version, reason, operator, and follow-up work in the
   incident notes, changelog, or release notes.

Release tags are evidence and must not be moved or reused. If a release is bad,
publish a new corrective version rather than changing the existing tag.

## Showing version in the UI

The UI footer renders `Version: <value>` from `APP_VERSION`.

Resolution order in code:

1. `APP_VERSION` environment variable.
2. `git describe --tags --always --dirty`.
3. short git SHA.
4. `dev` fallback.

### How to verify locally

```bash
cd app
APP_VERSION=v1.2.3 python manage.py runserver
```

Open the app and confirm footer shows `Version: v1.2.3`.
