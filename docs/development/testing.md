# Testing Coverage for Locality Geological Times

_Last updated: 2025-10-24_

## Relevant Test Modules
- `app/cms/tests/test_models.py` &mdash; validates `Locality.clean()` behaviour, default values, and django-simple-history snapshots for geological times.
- `app/cms/tests/test_forms.py` &mdash; exercises `LocalityForm` save/initialisation paths to confirm the multi-select widget persists abbreviations while rendering labels.
- `app/cms/tests/test_filters.py` &mdash; verifies the locality filter builds `JSONField` containment queries for single and multiple geological time selections.
- `app/cms/tests/test_views.py` &mdash; asserts locality list, detail, and print views render geological time labels, include accession counts, and surface the legend ordering expected by stakeholders.
- `app/cms/tests/test_resources.py` &mdash; guards the import/export widget so CSV round-trips accept abbreviations or labels and export readable names even when django-import-export passes optional keyword arguments.

## How to Run the Suite Locally
Execute the tests from the repository root so Django can locate the project package:

```bash
export DJANGO_SETTINGS_MODULE=app.config.settings
export PYTHONPATH=$(pwd)
pytest app/cms/tests/test_models.py \
       app/cms/tests/test_forms.py \
       app/cms/tests/test_filters.py \
       app/cms/tests/test_views.py \
       app/cms/tests/test_resources.py
```

Running the modules together mirrors the CI job that enforces coverage for the locality geological time feature set.

## Additional Checks
- The print view template is intentionally covered by integration tests; when modifying the markup, update `test_locality_print_view_orders_two_columns_and_shows_legend` accordingly.
- Import/export changes should always extend `test_geological_times_widget_*` parametrisations to include new edge cases (for example, translated labels or additional geological periods).

## Accession Detail Layout QA Checklist

_Last updated: 2025-02-15_

### Automated Verification

1. From the repository root, export the Django settings module and Python path so pytest can boot the project:

   ```bash
   export DJANGO_SETTINGS_MODULE=app.config.settings
   export PYTHONPATH=$(pwd)
   ```

2. Execute the regression suite that guards the three-panel layout, media trigger markup, and hover preview accessibility attributes:

   ```bash
   python -m pytest tests/accessions/test_accession_media_preview.py
   ```

3. Capture coverage to confirm the regression suite exercises at least 90% of the targeted code paths. The standard library `trace` module ships with Python and avoids extra dependencies:

   ```bash
   python -m trace --count --summary \
     --coverdir=.trace-accession-detail \
     --ignore-dir=/root/.pyenv/versions/3.11.12/lib/python3.11 \
     --ignore-dir=/root/.pyenv/versions/3.11.12/lib/python3.11/site-packages \
     --module pytest tests/accessions/test_accession_media_preview.py
   ```

   The summary should report 100% coverage for `tests/accessions/test_accession_media_preview.py`, satisfying the ≥90% requirement. Remove the temporary `.trace-accession-detail` directory after review.

### Manual Verification

- **Large screens (≥1367px):** Confirm the upper grid renders “Accession overview” on the left and places “Specimen details” and “Related field slips” above “Horizon” on the right (`app/cms/templates/cms/partials/accession_preview_panel.html`).
- **Hover preview centering:** Hover or focus any media thumbnail and ensure the enlarged preview (managed by `app/cms/static/cms/js/accession_media_preview.js`) appears centered at approximately twice the thumbnail size, while the click handler still opens the asset in a new tab.
- **Keyboard support:** Tab to each preview trigger and press `Enter`/`Space` to ensure the focus-visible state reveals the overlay and the `Escape` key dismisses it.
- **Small and medium screens:** Resize the viewport below 1367px and verify the layout stacks vertically with the preview overlay pinned near the trigger instead of the viewport center.

### Rollout Plan

1. Deploy the Django application and run `python manage.py collectstatic --noinput` so the updated CSS and JavaScript assets reach the CDN.
2. Flush any reverse proxy or CDN cache for `/static/cms/js/accession_media_preview.js` and `/static/css/style.css` to prevent stale hover behaviour.
3. Smoke test the accession detail page on staging using the manual steps above before promoting to production.

### Rollback Strategy

1. Revert the feature commit in Git and redeploy.
2. Re-run `python manage.py collectstatic --noinput` to restore the prior asset bundle and purge caches for the affected static files.
3. Spot-check the accession detail page to confirm the legacy layout and thumbnail interactions are restored.

## Tooth-marking CI hardening checks (TM-005)

Run these checks from the repository root for tooth-marking regression validation and CI parity:

```bash
pytest -q app/cms/tests/test_tooth_marking_detection_normalization.py \
         app/cms/tests/test_tooth_marking_integration.py \
         app/cms/tests/test_tooth_marking_debug_command.py \
         tests/cms/test_tooth_markings_service.py
```

```bash
pytest -q --cov=cms.tests.test_tooth_marking_detection_normalization \
         --cov-report=term-missing --cov-fail-under=90 \
         app/cms/tests/test_tooth_marking_detection_normalization.py
```

```bash
cd app && python manage.py makemigrations --check --dry-run
```

Documentation checks should run using repository tooling only. Do not run MkDocs commands for this project.

## FieldSlip sedimentary regression suite (FS-SED-006)

Use this suite when modifying field slip sedimentary forms, detail rendering, list filters, or queryset loading.

### Targeted coverage

The regression module validates:

- Sedimentary section ordering on detail pages (before Related accessions).
- Sedimentary field persistence through `/fieldslips/<id>/edit/`.
- Sedimentary filter behavior on `/fieldslips/`, including deduplicated results for M2M joins.

### Commands

Run from repository root:

```bash
pytest -q tests/cms/test_fieldslip_sedimentary_regressions.py
```

```bash
cd app && python manage.py check
```

```bash
cd app && python manage.py makemigrations --check
```

If your environment does not provide a local MySQL socket, Django may emit a migration-history warning during `makemigrations --check`; treat this as an environment warning when the command still returns `No changes detected`.

