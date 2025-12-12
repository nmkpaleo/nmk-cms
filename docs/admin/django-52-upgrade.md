# Django 5.2 upgrade notes for admins

These notes summarise what administrators should expect after the platform moves to Django 5.2 and how to validate or roll back the change.

## What changed
- Admin flat file import helper now requires `is_staff` and uses standard admin messaging for success/failure.
- CSRF trusted origins validation is stricter; host entries must include a scheme (e.g., `https://cms.example.org`).
- Unique constraints on accession, field slip, and preparation relationships now surface as database constraint errors instead of legacy `unique_together` messages.

## Validation checklist
- Sign in as a staff user and confirm the flat file import form renders and processes uploads. Non-staff should receive a 403.
- Run a sample accession create/edit to ensure constraint violations display inline errors when duplicate accessions or related rows are submitted.
- Verify admin login, password reset, and session expiry continue to operate as before.

## Rollback guidance
- Coordinate with developers to redeploy the previous dependency set and reverse migration `0076_alter_accession_unique_together_and_more` if constraint handling must revert.
- Restore prior `TRUSTED_ORIGINS` configuration if CSRF validation blocks admin logins after rollback.
