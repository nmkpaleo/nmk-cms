# Locality detail template inspection (Task T3)

## View context
- `LocalityDetailView` (`app/cms/views.py`) provides the `locality` instance as `context_object_name` alongside the paginated `accessions` queryset and pagination helpers (`page_obj`, `is_paginated`).
- Access control: `can_view_restricted` is true for authenticated superusers or users in the "Collection Managers" or "Curators" groups. When false, the accession queryset is filtered to `is_published=True` before pagination and enrichment via `prefetch_accession_related` and `attach_accession_summaries`.
- The context flag `show_accession_staff_columns` mirrors `can_view_restricted` so templates can toggle staff-only columns in accession lists.

## Template structure and headings
- Template path: `app/cms/templates/cms/locality_detail.html`, extending `base_generic.html` with W3.CSS and Font Awesome conventions.
- The associated accessions heading is set with `{% blocktrans asvar associated_accessions_title %}Associated accessions{% endblocktrans %}` and passed to `cms/partials/accession_basic_list.html` via `section_title`. The empty state uses `{% blocktrans asvar associated_accessions_empty %}No accessions found.{% endblocktrans %}`.
- The include receives `accessions`, `section_id="locality-accessions"`, `section_title`, `empty_message`, and `show_staff_columns` (bound to `show_accession_staff_columns`), so the partial handles table headings and staff-only columns based on the computed flag.
- Edit actions for the locality header are visible to superusers or members of the "Collection Managers" group, controlled directly in the template with `user` checks.
