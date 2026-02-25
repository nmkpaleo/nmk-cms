# Field-slip OCR/QC rollout checklist

Use this checklist when releasing field-slip OCR prompt, QC form, and approval
ingestion changes.

## CI and local verification

Run these commands before merge:

- `cd app && python manage.py check`
- `cd app && python manage.py makemigrations --check --dry-run`
- `cd app && python manage.py test cms.tests`
- `cd app && python manage.py test cms.tests.test_fieldslips.FieldSlipFilterTests cms.tests.test_fieldslips.FieldSlipListPermissionTests`
- `python -m pytest tests/docs`

For CI parity, coverage remains enforced with `pytest --cov --cov-fail-under=90`
in staging/prod workflows.

## Docs verification policy

Documentation is plain Markdown in `/docs`. Do not run MkDocs commands.
Use docs tests (`tests/docs`) and repository markdown checks instead.

## Staging smoke checks

1. Process a field-slip sample through intern QC and expert QC.
2. Confirm structured field-slip values are editable in wizard sections.
3. Approve and verify:
   - FieldSlip is created or updated,
   - relation mappings are applied,
   - no duplicate accession links are created on repeat approvals.
4. Confirm field-slip list filters still paginate correctly.

## Rollback

If OCR/QC output quality regresses:

1. Pause expert approvals.
2. Roll back to previous application release.
3. Re-open affected cards from QC queues and re-run expert approval.
4. Record rollback rationale in release notes and changelog.
