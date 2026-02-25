# Pagination Filter Persistence Audit

## Scope
This audit reviews filtered list pages that rely on shared pagination and verifies whether active GET filter parameters are preserved when users move between pages.

## Reviewed pages

### Accessions
- Route: `/accessions/`
- View type: `FilterView` with `AccessionFilter`
- Pagination: enabled (`paginate_by = 10`)
- Template: accession list extends the shared base template

### Localities
- Route: `/locality/`
- View type: `FilterView` with `LocalityFilter`
- Pagination: enabled (`paginate_by = 10`)
- Template: locality list extends the shared base template

## Shared pagination behavior
The shared pagination links in the base layout currently build URLs as `{{ request.path }}?page=...`.

This pattern replaces the full query string with only the page parameter. As a result, active filters are removed when moving to the next or previous page.

## Reproducible failure mode

### Accessions checklist
1. Open the Accessions list page.
2. Apply at least one filter (for example, specimen number prefix, taxon, or organisation).
3. Confirm the results are filtered.
4. Click **Next** or **Previous** pagination controls.
5. Observe that filter parameters are no longer present in the URL query string.
6. Observe that the result set falls back to the unfiltered list.

### Localities checklist
1. Open the Localities list page.
2. Apply at least one filter (for example, abbreviation, name, or geological time).
3. Confirm the results are filtered.
4. Click **Next** or **Previous** pagination controls.
5. Observe that filter parameters are no longer present in the URL query string.
6. Observe that the result set falls back to the unfiltered list.

## Affected surfaces identified
- Accessions filtered list pagination
- Localities filtered list pagination
- Any other list view inheriting the same shared pagination block without query-string preservation

## Recommendation for the follow-up implementation task
Use shared query-string-preserving pagination in the base template so this is fixed once and applied consistently across inheriting list pages.

