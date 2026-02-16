# Review workflow (admin)

This guide covers operating the specimen list review workflow.

## Feature flag
- Setting: `FEATURE_REVIEW_UI_ENABLED`
- Default: enabled (`1`)
- Disable with `0` to temporarily hide review queue, OCR queue, and page review endpoints.

## Operational checks
1. Confirm users have review permissions.
2. Confirm queue pages are visible and filterable.
3. Verify approved pages open in read-only mode via **View**.

## Approval outcomes
Approvals can create or update:
- Accessions and accession rows
- Field slips and accession-field-slip links
- Identification and specimen nature records
- Linked media for approved page images

Taxon qualifiers are split from free-text names and stored in the identification qualifier fields.

## Rollback
If issues are found during rollout:
1. Set `FEATURE_REVIEW_UI_ENABLED=0`
2. Restart web workers
3. Continue investigation without exposing UI actions to staff
