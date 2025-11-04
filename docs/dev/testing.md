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
