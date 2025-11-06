# Accession detail view structure audit

## View: `AccessionDetailView`
- Located in `app/cms/views.py` (`class AccessionDetailView`).
- Inherits from `django.views.generic.DetailView`.
- `template_name`: `cms/accession_detail.html`.
- `context_object_name`: `accession` (an instance of `cms.models.Accession`).
- Queryset behaviour:
  - `select_related('collection', 'specimen_prefix', 'accessioned_by')` to reduce queries.
  - Non managers/curators/public only see `is_published=True` records.
  - Prefetch helpers: `prefetch_accession_related` plus explicit `Prefetch` calls for:
    - `fieldslip_links` (`AccessionFieldSlip` + related `FieldSlip`).
    - `specimen_geologies` (`SpecimenGeology` + `earliest/latest_geological_context`).
    - `comments` ordered newest-first (`Comment` + `subject`).
    - `accessionreference_set` (`AccessionReference` + `Reference`).
- `get_context_data` enriches template context with:
  - `related_fieldslips`: `AccessionFieldSlip` list.
  - `references`: `AccessionReference` list.
  - `geologies`: `SpecimenGeology` list.
  - `comments`: `Comment` list.
  - `add_fieldslip_form`: blank `AccessionFieldSlipForm` (used to link existing slips).
  - `accession_rows`: all related `AccessionRow` records.
  - `first_identifications` + `identification_counts`: data returned by `build_accession_identification_maps`.
  - `taxonomy_map`: mapping of identification → `Taxon` details (duplicated under `taxonomy` for backwards compatibility).

## Template composition
Template extends `base_generic.html` and assembles three logical areas that will be reworked by later tasks.

### Header (`cms/accession_detail.html`)
- `<main>` container with page heading, collection label, and an edit button visible to superusers or users in the "Collection Managers" group.
- Includes `cms/partials/accession_preview_panel.html` (core summary card cluster).

### Comments section (`cms/accession_detail.html`)
- `<section>` with comments table or empty-state text.
- Add comment button available to authenticated collection managers.

### Related field slips section (`cms/accession_detail.html`)
- Entire section wrapped in permission check (superuser or collection manager).
- Contains:
  - Listing table (`related_fieldslips`).
  - Form block using `add_fieldslip_form` to link existing slips.
  - Button to open modal for creating a new field slip (iframe-based modal).
  - Modal markup and inline JS (`openFieldSlipModal`, `closeFieldSlipModal`, `closeModalAndRefresh`).

### Partial: `cms/partials/accession_preview_panel.html`
Organised into multiple `<section>` blocks:
1. **Accession overview** (`<article>` left column)
   - Displays accession metadata (number, locality, type status, accessioned by, general comment).
2. **Horizon** (`<article>` right column)
   - Table of `geologies` with add button for collection managers.
3. **Specimen details**
   - Table of `accession_rows` and related `NatureOfSpecimen` and taxonomy summaries using `first_identifications` / `taxonomy_map`.
4. **References**
   - Table of `references` with add button when permitted.
5. **Field slips preview (preview mode only)**
   - Conditionally rendered when `preview_mode` truthy (used by wizards/exports).
6. **Media**
   - Table of uploaded media (`accession.media`), showing inline image thumbnail when type is `photo`.

### Permissions & conditionals
- All add/edit CTAs are gated by checks against `user.is_authenticated`, `user.is_superuser`, and membership in the "Collection Managers" group.
- `preview_mode` flag suppresses management controls and shows simplified read-only views.

### Static resources
- Current template relies solely on inline JS (modal helpers) and W3.CSS classes; no dedicated static bundle.
- Font Awesome icons already embedded across sections.

## Integration points for future layout work
- Responsive adjustments should target `<section>` blocks in both `cms/accession_detail.html` and `cms/partials/accession_preview_panel.html`.
- Media hover enhancements will augment the `<img>` preview inside the Media table without altering existing onclick behaviour.
- Any new scripts/styles can live under `app/cms/static/cms/` alongside existing assets (none currently specific to this page).
