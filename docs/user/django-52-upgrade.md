# Django 5.2 upgrade notes for users

The CMS now runs on Django 5.2 LTS. The items below summarise what end users should expect and how to report issues.

## What changed
- FieldSlip Select2 autocomplete endpoints require you to be signed in; anonymous requests no longer return results.
- Accession list filters include improved ARIA state updates so screen readers announce when filter panels open or close.
- Password reset emails retain the three-day expiry but honour any environment-specific override set by operations.

## How to verify your workflows
- Ensure you are logged in before using FieldSlip search widgets; if results do not appear, reauthenticate and retry.
- Open and close the accession list filter accordion to confirm it announces state changes in your screen reader.
- Request a password reset to confirm the email link works within the expected expiry window.

## Rollback expectations
If a rollback is triggered, the platform may briefly revert to the previous Django 4.2 experience. Re-test autocomplete and filter behaviour and report discrepancies to the support team.
