# Accession number series: current implementation audit

## Model and validation
- **Model**: `AccessionNumberSeries` lives in `cms.models` with fields `user`, `start_from`, `end_at`, `current_number`, `is_active`, plus `HistoricalRecords` tracking. Validation enforces `start_from < end_at`, prevents overlapping ranges within the same pool (TBI vs shared users), and allows only one active series per user. Save calls `full_clean()` first.
- **Pools**: TBI user (`username == 'tbi'`, case-insensitive) is validated against other TBI ranges only; all other users share a single pool validated against non-TBI ranges.

## Forms
- **AccessionBatchForm** (`cms.forms`): staff-facing batch creation form exposing `user`, `count` (1–500), `collection`, and `specimen_prefix`. The `user` queryset is limited to users with active series; labels include remaining numbers in the series.
- **AccessionNumberSeriesAdminForm** (`cms.forms`): admin add/edit form. On add, `start_from`/`current_number` become read-only, `is_active` defaults hidden/true, and count is required via a custom field. Clean populates start/current using pool-specific next-start logic (dedicated TBI pool starting at 1,000,000; shared pool starting at 1), and blocks multiple active series per user. Save sets `end_at = start_from + count - 1` for new records. Widget metadata exposes JSON for client-side previews.

## Views and routing
- **Dashboard** (`cms.views.dashboard`): populates `has_active_series = AccessionNumberSeries.objects.filter(user=request.user, is_active=True).exists()` for Collection Managers. Template `cms/dashboard.html` shows the Collection Management card only for the group; within it, the “Generate batch” link appears only when `has_active_series` is true.
- **Batch generation view** (`cms.views.generate_accession_batch`): `@staff_member_required`, uses `AccessionBatchForm`. On POST, it fetches the selected user’s active series and calculates remaining/range for template messaging. Accessions are created via `generate_accessions_from_series`; success redirects to `accession_list`, otherwise attaches errors to the form.
- **URL**: routed at `/accessions/generate-batch/` via `accession-generate-batch` (in `cms/urls.py`).

## Utilities and numbering
- **`generate_accessions_from_series`** (`cms.utils`): fetches active series for the target user, validates the requested count against `end_at`, instantiates `Accession` objects for the given collection/prefix, advances `current_number` accordingly, saves all accessions individually, and returns the created list. Raises `ValueError` if no active series or range exhausted.

## Tests
- `AccessionNumberSeriesAdminFormTests` cover TBI vs shared pool sequencing, widget metadata, and count-derived range creation. `generate_accessions_from_series` tests validate counter increments, accession creation, and missing-series failure paths.
