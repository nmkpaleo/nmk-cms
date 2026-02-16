# Django 5.2 Upgrade Playbook

This guide documents how to roll out and validate the Django 5.2 LTS upgrade across environments. It highlights dependency changes, configuration updates, behavioural shifts, and rollback procedures specific to this release.

## Summary of changes
- Dependencies now pin **Django 5.2**, with updated `asgiref` and `sqlparse` requirements.
- Host and CSRF trusted origin parsing trims whitespace and auto-adds `https://` for bare host entries to satisfy Django 5.2 validation.
- Password reset token lifetime is configurable via `PASSWORD_RESET_TIMEOUT` with a three-day default to match Django 5.2.
- `USE_DEPRECATED_PYTZ` is disabled to rely on Python zoneinfo.
- Legacy `unique_together` definitions were replaced with named `UniqueConstraint` metadata via migration `0076_alter_accession_unique_together_and_more`.
- FieldSlip Select2 autocomplete endpoints now require authentication, and the admin flat file import helper is limited to staff.

## Upgrade steps
1. Install dependencies:
   ```bash
   pip install -r app/requirements.txt
   ```
2. Apply migrations (expects MySQL 8+):
   ```bash
   python manage.py migrate
   ```
3. Verify environment configuration:
   - Ensure `ALLOWED_HOSTS` is comma-separated without extra spaces.
   - Set `TRUSTED_ORIGINS` with schemes (e.g., `https://example.org`) so CSRF validation passes.
   - Optionally override `PASSWORD_RESET_TIMEOUT` if a different expiry is required.
4. Smoke-test critical flows:
   - Confirm login, logout, and password reset emails continue to send and respect the configured timeout.
   - Validate admin flat file imports as a staff user; non-staff should receive a 403.
   - Exercise FieldSlip autocomplete from Select2 widgets while authenticated and ensure unauthenticated requests are rejected.
   - Review accession create/edit flows touching the new unique constraints to ensure error messaging surfaces correctly.

## Behaviour notes
- CSRF trusted origins must include a scheme; bare hosts are automatically prefixed with `https://` but should be supplied with a scheme in production.
- The password reset token expiry defaults to 72 hours; operations can shorten or extend it per deployment.
- Database uniqueness now relies on explicit constraints. Admins will see standard constraint violation errors rather than legacy `unique_together` messaging.
- Select2 autocomplete endpoints for FieldSlips enforce authentication to prevent anonymous enumeration.
- The admin flat file import helper now checks `is_staff` before rendering the form to align with Django 5.2 admin expectations.

## Testing and verification
Run the following checks after deployment:
- `pytest` (focus on `tests/cms/test_upgrade_regressions.py` for authentication coverage).
- `python manage.py check --deploy` to confirm settings (hosts, CSRF, secure cookies) are correct.
- `python -m compileall app` to catch import regressions.

## Deployment assets
- **Docker entrypoint** now binds Gunicorn to `0.0.0.0:8000` and accepts tuning via `GUNICORN_BIND`, `GUNICORN_WORKERS`, `GUNICORN_TIMEOUT`, `GUNICORN_MAX_REQUESTS`, and `GUNICORN_MAX_REQUESTS_JITTER` environment variables. Defaults are safe for staging/prod; override per environment as needed.
- **Compose defaults** set `DJANGO_SETTINGS_MODULE=config.settings` for web containers to align with the Django 5.2 settings module.
- **CI workflows** for staging and production compile the Django project (`python -m compileall app`) before building images to surface syntax errors introduced during the upgrade.

## Rollout checklist (staging → production)
1. Export Django 5.2-ready images using the updated GitHub Actions workflows, confirming the compile step passes.
2. Deploy to staging with the refreshed compose files, setting any Gunicorn overrides through environment variables and ensuring `TRUSTED_ORIGINS` contains schemes.
3. Run `python manage.py check --deploy` and smoke tests (auth flows, admin import, autocomplete) against staging.
4. Promote the tested image to production and re-run smoke tests plus cache/DB connection checks.

## Rollback plan
1. Revert to the previous dependency set (Django 4.2.x) and redeploy.
2. Reverse migration `0076_alter_accession_unique_together_and_more` if necessary:
   ```bash
   python manage.py migrate cms 0075
   ```
3. Restore prior environment variables for hosts/CSRF configuration.
4. Re-run smoke tests (auth, admin imports, autocomplete) to confirm behaviour matches the pre-upgrade state.
