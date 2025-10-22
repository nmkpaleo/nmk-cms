# CMS Template and CSS Inventory

_Last updated: 2026-03-01_

## Layout Dependency Summary (Pre-Refactor)

| View Type | Primary Templates | W3.CSS Usage | Local CSS / JS Touchpoints | Notes for Refactor |
| --- | --- | --- | --- | --- |
| List & Search | `cms/*_list.html` variants (accession, drawer, fieldslip, locality, place, preparation, reference, storage) | Shared header rows, filter accordions, and table shells lean on `w3-container`, `w3-row-padding`, `w3-table-all`, and `w3-responsive`.【F:app/cms/templates/cms/accession_list.html†L8-L108】【F:app/cms/templates/cms/reference_list.html†L8-L123】 | Each template embeds a small `toggleAccordion` helper and duplicates the accordion markup; no bespoke CSS classes beyond inherited typography utilities.【F:app/cms/templates/cms/accession_list.html†L24-L109】 | Extract accordion into an include and switch to a shared stimulus/alpine controller to avoid per-template JS duplication. |
| Detail | `cms/*_detail.html` (accession, accession_row, drawerregister, fieldslip, locality, place, preparation, reference, storage) | Cards, summary grids, and related tables now standardise on `<main>/<section>` landmarks, `w3-card`, and Font Awesome section icons for quick scanning.【F:app/cms/templates/cms/accession_detail.html†L1-L135】【F:app/cms/templates/cms/preparation_detail.html†L1-L221】 | History tables and related lists share the same W3 table shell; no bespoke CSS classes remain. | Future enhancements: extract history table rows into a shared include and align curator action buttons with a button helper. |
| Detail + Sub-list | `cms/locality_detail.html`, `cms/storage_detail.html` | Combine W3 cards for the primary object with responsive related-object tables and Font Awesome headings.【F:app/cms/templates/cms/locality_detail.html†L1-L107】 | Manual pagination components mirror the helper used in list templates and rely solely on W3 bar/button classes.【F:app/cms/templates/cms/storage_detail.html†L108-L147】 | Align pagination markup with a single include referenced by both list and detail pages to reduce drift. |
| Dashboard | `cms/dashboard.html`, `cms/qc/dashboard_queue.html` | Uses `w3-table` and `w3-row-padding` layouts for role cards and queue tables.【F:app/cms/templates/cms/dashboard.html†L8-L108】【F:app/cms/templates/cms/qc/dashboard_queue.html†L1-L74】 | Queue partial expects context dicts and renders CTA buttons; no extra CSS beyond W3, but inline `<ul>` lists lack shared styling. | Convert repeated headings/empty states into macros or includes and apply W3 alert classes for empty states to ensure consistency. |
| Forms & Wizards | `cms/*_form.html`, `cms/*_wizard*.html`, `cms/add_accession_*` | Standalone forms rely on `base_form.html` plus W3 error colouring (`w3-text-red`) and card wrappers in the parent templates.【F:app/cms/templates/includes/base_form.html†L1-L55】【F:app/cms/templates/cms/accession_form.html†L1-L22】 | `base_form.html` mixes custom table-based layout with inline button styling and lacks W3 button classes; wizard templates add per-step scripts via formset JS includes.【F:app/cms/templates/includes/base_form.html†L23-L55】 | Replace table layout with W3 grid utilities and move inline button styling to W3 button classes; ensure wizard navigation uses shared components. |
| History / Audit | `cms/qc/history.html`, history tables embedded in detail templates | Audit tables use `w3-table-all`, `w3-small`, and Font Awesome icons for back links.【F:app/cms/templates/cms/storage_detail.html†L148-L170】 | No dedicated include for history rows; each template iterates its own `history_entries` rendering. | Introduce a reusable partial for history entries and annotate column headers with `<abbr>`/ARIA to aid screen readers. |
| Media / Upload | `cms/preparation_media_upload.html`, `cms/upload_media.html`, `cms/fieldslip_import.html` | `upload_media.html` reuses the shared form include (minimal W3) while `preparation_media_upload.html` renders a raw form without W3 wrappers.【F:app/cms/templates/cms/upload_media.html†L1-L9】【F:app/cms/templates/cms/preparation_media_upload.html†L1-L15】 | `fieldslip_import.html` depends entirely on bespoke `.template_import` styles from `style.css`, and `preparation_media_upload.html` retains Bootstrap-like `.btn` classes with no definitions.【F:app/cms/templates/cms/fieldslip_import.html†L1-L19】【F:app/cms/static/css/style.css†L205-L284】 | Move all upload interfaces onto W3 cards/buttons via the shared form include or a new component; migrate custom drag/drop styling to W3 utility equivalents. |
| Inventory | `inventory/start.html`, `inventory/session.html` | Uses `w3-row`, `w3-col`, `w3-card`, and modal helpers to present scanning workflows.【F:app/cms/templates/inventory/session.html†L1-L120】 | Custom JS drives scanning feedback and toggles classes such as `w3-pale-green`/`w3-pale-red`; no extra CSS beyond inline `<script>`. | Document which DOM hooks the JS expects before replacing custom status markup with W3 alert components. |

The matrix below expands on individual template expectations, context variables, and permission constraints prior to the W3.CSS-centric refactor.

## Template Inventory

### Layout & Entry Points
| Template | Path | Primary Use | Notes |
| --- | --- | --- | --- |
| Base layout | `app/cms/templates/base_generic.html` | Primary CMS shell with navigation, pagination block, and static asset loading. | Provides global nav, W3.CSS integration, and hooks for Select2 assets. |
| Public landing page | `app/cms/templates/index.html` | Marketing-style hero landing for unauthenticated visitors. | Uses hero classes from `style.css` and static imagery. |

### Dashboard & Workflow Views
| Template | Path | Primary Use | Notes |
| --- | --- | --- | --- |
| CMS dashboard | `app/cms/templates/cms/dashboard.html` | Role-aware dashboard summarizing preparations, accessions, and QC queues. | Includes the QC dashboard partial and links to creation flows. |
| QC queue (partial) | `app/cms/templates/cms/qc/dashboard_queue.html` | Embeds QC backlog metrics inside dashboards. | Shared by the main dashboard and QC wizard pages. |
| Inventory start | `app/cms/templates/inventory/start.html` | Start screen for physical inventory sessions. | Basic multi-select of shelves before launching a session. |
| Inventory session | `app/cms/templates/inventory/session.html` | Interactive session interface for inventory scanning/updating. | Contains inline JS for fetch-based updates and barcode scanning feedback. |

### List & Search Views
| Template | Path | Primary Use | Notes |
| --- | --- | --- | --- |
| Accessions list | `app/cms/templates/cms/accession_list.html` | Filterable accession listing with bulk filter panel. | Leverages FilterView forms for taxonomy and metadata fields. |
| Drawer list | `app/cms/templates/cms/drawerregister_list.html` | Filterable list of drawers with drag-to-reorder support. | Includes drag handle column when user can edit. |
| Field slip list | `app/cms/templates/cms/fieldslip_list.html` | Table of field slips with inline access to aerial photos. | Uses W3 responsive table styling. |
| Locality list | `app/cms/templates/cms/locality_list.html` | Filtered locality listing with summarised data. | Shares filter toggling pattern with other list templates. |
| Place list | `app/cms/templates/cms/place_list.html` | Filter/search interface for places. | Presents address metadata in table format. |
| Preparation list | `app/cms/templates/cms/preparation_list.html` | List of specimen preparations with status filtering. | Gate-kept by preparation access mixin. |
| Reference list | `app/cms/templates/cms/reference_list.html` | Bibliographic reference catalog list. | Integrates filter form for citation metadata. |
| Storage list | `app/cms/templates/cms/storage_list.html` | Storage location overview with filterable attributes. | Includes create CTA for collection managers. |
| Accession row list (wizard) | `app/cms/templates/cms/qc/rows_step.html` | Step in QC workflow that lists accession rows for review. | Renders row cards via the shared partial. |
| QC media queue | `app/cms/templates/cms/qc/media_queue_list.html` | Media QC backlog listing for staff review. | Backed by `MediaQCQueueView`. |

### Detail Views
| Template | Path | Primary Use | Notes |
| --- | --- | --- | --- |
| Accession detail | `app/cms/templates/cms/accession_detail.html` | Full accession profile with related records. | Links to preview partial for nested relationships. |
| Accession row detail | `app/cms/templates/cms/accession_row_detail.html` | Single accession row detail, including identifications/specimens. | Used in QC preview and direct navigation. |
| Drawer detail | `app/cms/templates/cms/drawerregister_detail.html` | Drawer metadata view with scanning details. | Shows aggregated counts and assigned users. |
| Field slip detail | `app/cms/templates/cms/fieldslip_detail.html` | Field slip record detail page with attachments. | Displays aerial photo when present. |
| Locality detail | `app/cms/templates/cms/locality_detail.html` | Locality context with map/location metadata. | Integrates referencing data where available. |
| Place detail | `app/cms/templates/cms/place_detail.html` | Place address and association detail view. | Accessible from locality/place lists. |
| Preparation detail | `app/cms/templates/cms/preparation_detail.html` | Shows preparation lifecycle, actions, and attachments. | Supports curator approval actions. |
| Reference detail | `app/cms/templates/cms/reference_detail.html` | Detailed reference view with citation metadata. | Linked from accessions and list pages. |
| Storage detail | `app/cms/templates/cms/storage_detail.html` | Storage area detail including capacity and child records. | Provides editing shortcut for managers. |

### Form, Wizard, and Action Templates
| Template | Path | Primary Use | Notes |
| --- | --- | --- | --- |
| Accession create/edit | `app/cms/templates/cms/accession_form.html` | General accession form wrapper. | Uses `includes/base_form.html` for layout. |
| Accession wizard | `app/cms/templates/cms/accession_wizard.html` | Multi-step accession creation wizard. | Pulls in add_* step partials for nested data. |
| Accession batch | `app/cms/templates/cms/accession_batch_form.html` | Batch accession number generation form. | Provides preview of generated ranges. |
| Accession row form | `app/cms/templates/cms/accession_row_form.html` | Inline form for individual accession rows. | Reused in wizard contexts. |
| Add accession comment | `app/cms/templates/cms/add_accession_comment.html` | Modal-like form for appending comments. | Submitted via wizard step actions. |
| Add accession geology | `app/cms/templates/cms/add_accession_geology.html` | Wizard step for geological metadata. | Works with dynamic formsets. |
| Add accession reference | `app/cms/templates/cms/add_accession_reference.html` | Wizard step to connect references. | Integrates Select2 reference widgets. |
| Add accession row | `app/cms/templates/cms/add_accession_row.html` | Container for adding nested row data. | Hosts specimen/identification sub-forms. |
| Add row identification | `app/cms/templates/cms/add_accession_row_identification.html` | Nested identification form for accession rows. | Renders dynamic formset entries. |
| Add row specimen | `app/cms/templates/cms/add_accession_row_specimen.html` | Nested specimen form for accession rows. | Works with JavaScript duplication logic. |
| Drawer form | `app/cms/templates/cms/drawerregister_form.html` | CRUD form for drawers. | Shares base form include. |
| Storage form | `app/cms/templates/cms/storage_form.html` | CRUD form for storage locations. | Shares base form include. |
| Field slip form | `app/cms/templates/cms/fieldslip_form.html` | Field slip add/edit form. | Uses W3 form controls and file inputs. |
| Field slip import | `app/cms/templates/cms/fieldslip_import.html` | CSV import UI for field slips. | Applies hero-style upload panel. |
| Locality form | `app/cms/templates/cms/locality_form.html` | Locality creation/edit form. | Shares base form include. |
| Place form | `app/cms/templates/cms/place_form.html` | Place creation/edit form. | Shares base form include. |
| Preparation form | `app/cms/templates/cms/preparation_form.html` | Preparation create/edit form. | Provides dynamic stepper for statuses. |
| Preparation approve | `app/cms/templates/cms/preparation_approve.html` | Curator approval confirmation. | Offers decision actions. |
| Preparation confirm delete | `app/cms/templates/cms/preparation_confirm_delete.html` | Deletion confirmation dialog. | Minimal content around confirm/cancel. |
| Preparation media upload | `app/cms/templates/cms/preparation_media_upload.html` | Upload interface for preparation assets. | Works with file multi-upload. |
| Reference form | `app/cms/templates/cms/reference_form.html` | CRUD form for references. | Relies on `template_form_*` CSS helpers. |
| Upload media | `app/cms/templates/cms/upload_media.html` | Generic media upload form. | Links to storage after success. |
| Base form include | `app/cms/templates/includes/base_form.html` | Shared form rendering include. | Centralizes CSRF, help text, and submit button. |
| QC wizard base | `app/cms/templates/cms/qc/wizard_base.html` | Parent template for QC workflows. | Embeds preview panel and history partials. |
| QC intern wizard | `app/cms/templates/cms/qc/intern_wizard.html` | Specialization of QC wizard for interns. | Extends wizard base with intern-specific steps. |
| QC expert wizard | `app/cms/templates/cms/qc/expert_wizard.html` | Expert-level QC interface. | Adjusts toolbars and available actions. |
| QC summary step | `app/cms/templates/cms/qc/summary_step.html` | Final QC summary panel. | Summarizes validations before submission. |

### History & Reporting
| Template | Path | Primary Use | Notes |
| --- | --- | --- | --- |
| QC history | `app/cms/templates/cms/qc/history.html` | History view of QC submissions. | Embeds the history list partial. |
| QC history list (partial) | `app/cms/templates/cms/qc/partials/history_list.html` | Reusable log list for QC history views. | Accepts flags for compact rendering. |
| QC reference card (partial) | `app/cms/templates/cms/qc/partials/reference_card.html` | Displays reference metadata inside QC flows. | Used within wizard review steps. |
| QC row card (partial) | `app/cms/templates/cms/qc/partials/row_card.html` | Renders row comparison cards in QC steps. | Supports template row duplication. |
| QC chip (partial) | `app/cms/templates/cms/qc/partials/chip.html` | Pills for representing nested forms. | Supports ident/specimen chips. |
| Accession preview panel (partial) | `app/cms/templates/cms/partials/accession_preview_panel.html` | Full preview of accession, field slips, and identifications using stacked W3 cards, semantic sections, and action buttons. | Shared between wizard and detail contexts; honours `preview_mode` to hide mutating controls. |

### Admin Overrides & Utilities
| Template | Path | Primary Use | Notes |
| --- | --- | --- | --- |
| Admin base | `app/cms/templates/admin/base_site.html` | Overrides admin chrome (logo, titles). | Extends default admin base. |
| Flat file import | `app/cms/templates/admin/flat_file_import.html` | Custom admin page for CSV import. | Provides w3-styled upload UI. |
| Upload scan | `app/cms/templates/admin/upload_scan.html` | Admin view for bulk scan uploads. | Contains direct file submit form. |
| OCR prompt | `app/cms/templates/admin/do_ocr_prompt.html` | Admin action confirmation for OCR jobs. | Provides status messaging. |
| ChatGPT usage report | `app/cms/templates/admin/chatgpt_usage_report.html` | Reporting page for AI usage metrics. | Tabular view of user requests. |
| Accession number series form | `app/cms/templates/admin/cms/accessionnumberseries/change_form.html` | Admin change form customization. | Provides inline helper text. |
| Merge candidate list | `app/cms/templates/admin/cms/merge/candidate_list.html` | Lists possible merge targets. | Loaded by merge admin `ListView`. |
| Merge search results | `app/cms/templates/admin/cms/merge/search_results.html` | Paginated search results for merge admin. | Includes paginator markup. |
| Merge manual confirm | `app/cms/templates/admin/cms/merge/manual_action_confirm.html` | Manual merge confirmation dialog. | Highlights selected records before action. |
| Merge compare | `app/cms/templates/admin/cms/merge/compare.html` | Side-by-side merge comparison UI. | Displays fields before merge. |
| Merge form | `app/cms/templates/admin/cms/merge/merge_form.html` | Form for executing merge actions. | Integrates merge admin JS. |

## CSS Asset Inventory

### Local Stylesheets
| File | Path | Purpose | Consumers |
| --- | --- | --- | --- |
| CMS global styles | `app/cms/static/css/style.css` | Houses global navigation, hero, form helper, and list/table styling. | Loaded via `base_generic.html` for all CMS pages and public landing. |
| Merge admin styles | `app/cms/static/css/merge_admin.css` | Styling for merge admin dashboard components. | Loaded by `MergeAdmin` via `Media` declaration in `admin_merge.py`. |

### Redundancy and Consolidation Opportunities
- **Unused or orphaned selectors in `style.css`:** Helper classes such as `.template_buttons`, `.list-page-header`, `.search-bar`, `.dropdown-list-select`, `.actions`, `.reset_button`, `.lists_table`, `.checkbox_list`, and `.table-container` do not appear in any CMS templates or widgets, indicating they can be pruned or relocated to domain-specific bundles.【F:app/cms/static/css/style.css†L151-L192】【F:app/cms/static/css/style.css†L280-L356】【F:app/cms/static/css/style.css†L826-L858】【F:app/cms/static/css/style.css†L1042-L1107】
- **Mismatched selector vs. markup:** `.step-link` is defined in the stylesheet, while the paginator markup uses `.step-links`, so the intended styling never applies.【F:app/cms/static/css/style.css†L1130-L1133】【F:app/cms/templates/admin/cms/merge/search_results.html†L59-L74】 Aligning class names will remove redundant CSS.
- **JavaScript toggles unused styles:** The mobile menu script toggles `.shifted` on the main content container, but `style.css` only styles `.hero_section_container.shifted`, leaving the transition unused. Consider updating the selector or removing the CSS/JS pairing.【F:app/cms/static/javascript.js†L1-L19】【F:app/cms/static/css/style.css†L973-L984】
- **Legacy pagination styles:** `.pagination`, `.pagination_previous`, and `.pagination_next` remain from earlier designs but all templates now use W3 pagination helpers from `base_generic.html`. These selectors can be retired once confirmed unused across non-CMS templates.【F:app/cms/static/css/style.css†L372-L423】【F:app/cms/templates/base_generic.html†L83-L131】
- **Redundant Select2 width overrides:** Global `.select2-container`/`.select2-selection` rules in `style.css` duplicate the inline `<style>` block in `base_generic.html`; consolidate to a single source to avoid drift.【F:app/cms/static/css/style.css†L892-L908】【F:app/cms/templates/base_generic.html†L21-L36】

### Follow-up Ideas
- Centralize frequently reused filter accordion markup into an include to reduce duplication across list templates.
- Split the current monolithic `style.css` into domain-specific bundles (public landing, CMS shell, forms, import flows) to simplify future audits.
- Document the expected CSS hooks for dynamically injected components (e.g., Select2, drag handles) within this guideline to aid future refactors.

### Template Context Matrix (2025-02)
The tables above capture high-level intent. This matrix inventories the concrete context requirements, reusable fragments, and authentication gates for every CMS template before refactoring. Unless otherwise noted, templates extend `base_generic.html` and inherit its HTML5 structure and W3.CSS baseline.

#### List & Search Templates
_Default context_: Django `ListView`/`FilterView` supplies `object_list` (e.g. `accessions`, `drawers`), `page_obj`, `paginator`, `is_paginated`, and `filter` (with `filter.form`) where applicable.

- **`cms/accession_list.html`**
  - Blocks: `title`, `content`, `script`
  - View: `AccessionListView` (`FilterView`)
  - Additional context: `user` for permission-aware columns; `accessions` preloaded with taxa/element summaries.
  - Reusable pieces: Inline accordion pattern for filters; no external includes.
  - Auth: Public read. Non-staff see only `is_published` rows via queryset guard.
- **`cms/drawerregister_list.html`**
  - Blocks: `title`, `content`, `script`
  - View: `DrawerRegisterListView` (`LoginRequiredMixin`, `DrawerRegisterAccessMixin`, `FilterView`)
  - Additional context: `can_edit` toggles reorder controls and drag handles.
  - Reusable pieces: Drag-and-drop script posts to `drawerregister_reorder` endpoint.
  - Auth: Staff/intern roles enforced by mixin; reorder requires elevated groups.
- **`cms/fieldslip_list.html`**
  - Blocks: `title`, `content`, `script`
  - View: `FieldSlipListView` (`LoginRequiredMixin`, `UserPassesTestMixin`, `FilterView`)
  - Additional context: none beyond filter + list; responsive column toggles rely on DOM IDs.
  - Auth: Restricted to Collection Managers via `test_func`.
- **`cms/locality_list.html`**
  - Blocks: `title`, `content`, `script`
  - View: `LocalityListView` (`FilterView`)
  - Additional context: `localities` alias populated by view; template expects filter fields `name` and `abbreviation`.
  - Auth: Public read.
- **`cms/place_list.html`**
  - Blocks: `title`, `content`, `script`
  - View: `PlaceListView` (`FilterView`)
  - Additional context: Filter requires `locality`, `name`, `place_type` fields.
  - Auth: Public read.
- **`cms/preparation_list.html`**
  - Blocks: `title`, `content`, `script`
  - View: `PreparationListView` (`LoginRequiredMixin`, `PreparationAccessMixin`, `FilterView`)
  - Additional context: Queryset annotation exposes `accession_label` used in template.
  - Auth: Curators, Collection Managers, and superusers via mixin.
- **`cms/reference_list.html`**
  - Blocks: `title`, `content`, `pagination`, `script`
  - View: `ReferenceListView` (`FilterView`)
  - Additional context: Template consumes `page_obj` for manual pagination block.
  - Auth: Public read.
- **`cms/storage_list.html`**
  - Blocks: `title`, `content`, `script`
  - View: `StorageListView` (`LoginRequiredMixin`, `CollectionManagerAccessMixin`, `FilterView`)
  - Additional context: `storages` alias includes counts and parent areas for display.
  - Auth: Collection Managers / superusers.
- **`cms/qc/media_queue_list.html`**
  - Blocks: `title`, `content`
  - View: `MediaQCQueueView` variants (`LoginRequiredMixin`, `UserPassesTestMixin`, `ListView`)
  - Additional context: `queue_title`, `queue_description`, `queue_action_label`, `queue_empty_message` strings; template reads `media_list` and `page_obj`.
  - Reusable pieces: Shared by multiple queue subclasses with differing filters.
  - Auth: Intern/expert gating controlled per subclass `allowed_roles`.

#### Detail Templates
_Default context_: Django `DetailView` supplies `object` (aliased per view) and `user`.

- **`cms/accession_detail.html`**
  - Blocks: `title`, `content`, `extra_scripts`
  - View: `AccessionDetailView` (public with queryset guard)
  - Additional context: `related_fieldslips`, `references`, `geologies`, `comments`, `accession_rows`, `first_identifications`, `identification_counts`, `taxonomy`, `add_fieldslip_form`.
  - Reusable pieces: Includes `cms/partials/accession_preview_panel.html`.
  - Auth: Public read; edit links limited to Collection Managers/superusers.
- **`cms/accession_row_detail.html`**
  - Blocks: `title`, `content`
  - View: `AccessionRowDetailView` (`DetailView`)
  - Additional context: `natureofspecimens`, `identifications`, `can_edit`, `can_manage`, `show_inventory_status`.
  - Auth: Public view; management actions hidden unless Collection Manager/superuser.
- **`cms/drawerregister_detail.html`**
  - Blocks: `title`, `content`
  - View: `DrawerRegisterDetailView` (`LoginRequiredMixin`, `DrawerRegisterAccessMixin`, `DetailView`)
  - Additional context: `history_entries`, `can_edit`.
  - Auth: Drawer access mixin ensures proper roles.
- **`cms/fieldslip_detail.html`**
  - Blocks: `title`, `content`
  - View: `FieldSlipDetailView`
  - Additional context: none beyond `fieldslip` object; template accesses media fields for aerial photo.
  - Auth: Public read.
- **`cms/locality_detail.html`**
  - Blocks: `title`, `content`
  - View: `LocalityDetailView`
  - Additional context: `accessions`, `page_obj`, `is_paginated` for the related accession list.
  - Auth: Public read.
- **`cms/place_detail.html`**
  - Blocks: `title`, `content`
  - View: `PlaceDetailView`
  - Additional context: `children` queryset of related places in addition to the `place` object.
  - Auth: Public read.
- **`cms/preparation_detail.html`**
  - Blocks: `title`, `content`
  - View: `PreparationDetailView` (`LoginRequiredMixin`, `DetailView`)
  - Additional context: `history_entries`, `can_edit`; template pulls related media directly via `preparation.preparationmedia_set`.
  - Auth: Curators, Preparators, Collection Managers based on `can_edit` logic; list access enforced by mixin.
- **`cms/reference_detail.html`**
  - Blocks: `title`, `content`
  - View: `ReferenceDetailView`
  - Additional context: `accession_entries` (accession/page tuples) and optional `doi_url`.
  - Auth: Public read.
- **`cms/storage_detail.html`**
  - Blocks: `title`, `content`
  - View: `StorageDetailView` (`LoginRequiredMixin`, `CollectionManagerAccessMixin`, `DetailView`)
  - Additional context: `specimen_page_obj`, `specimens`, `specimen_count`, `children`, `history_entries`, `can_edit`.
  - Auth: Collection Managers / superusers.

#### Dashboard Template
- **`cms/dashboard.html`**
  - Blocks: `title`, `content`
  - View: `dashboard` function view
  - Context: `is_preparator`, `my_preparations`, `priority_tasks`, `is_curator`, `completed_preparations`, `is_collection_manager`, `has_active_series`, `unassigned_accessions`, `latest_accessions`, `is_intern`, `my_drawers`, `qc_sections`, `qc_extra_links`, `no_role`.
  - Reusable pieces: Includes `cms/qc/dashboard_queue.html`; relies on timer JS for intern scan tracking.
  - Auth: Expects authenticated users; role flags derived from group membership.

#### Form & Action Templates
_Default context_: Forms expose `form`, `form.media`, CSRF token, and `request`.

- **`cms/accession_batch_form.html`** — Blocks `title`, `content`; expects `form`, `series_remaining`, `series_range`, plus `title`, `method`, `action` strings from `generate_accession_batch` (`@staff_member_required`).
- **`cms/accession_form.html`** — Blocks `title`, `content`; requires `form` and `request.path`. Used by `accession_create` and `accession_edit` (edit requires Collection Manager login).
- **`cms/accession_row_form.html`** — Blocks `title`, `content`; expects `form`, `accessionrow`, `request.path`; served by `AccessionRowUpdateView` (login + Collection Manager check).
- **`cms/accession_wizard.html`** — Blocks `title`, `head`, `content`, `extra_scripts`; uses `wizard` context from `AccessionWizard` (steps metadata, `wizard.management_form`, per-step `wizard.form`, `wizard.steps`).
- **`cms/add_accession_comment.html`** — Blocks `title`, `content`; expects `form`, `accession`; guarded by `@login_required` + Collection Manager test.
- **`cms/add_accession_geology.html`** — Blocks `title`, `content`; expects `form`, `accession`; guarded by `@login_required` + Collection Manager test.
- **`cms/add_accession_reference.html`** — Blocks `title`, `content`; expects `form`, `accession`; guarded by `@login_required` + Collection Manager test.
- **`cms/add_accession_row.html`** — Blocks `title`, `content`; expects `form`, `accession`; view enforces Collection Manager login before saving.
- **`cms/add_accession_row_identification.html`** — Blocks `title`, `content`; expects `form`, `accession_row`; view restricted to Collection Managers (`@login_required`, `user_passes_test`).
- **`cms/add_accession_row_specimen.html`** — Blocks `title`, `content`; expects `form`, `accession_row`; same auth guard as identification.
- **`cms/drawerregister_form.html`** — Blocks `title`, `content`; requires `form`, `request.path`; used by `DrawerRegisterCreateView`/`UpdateView` (login + drawer access mixin).
- **`cms/fieldslip_form.html`** — Blocks `title`, `content`; expects `form`; used by `fieldslip_create`/`fieldslip_edit` (functions without decorators, but exposed in staff navigation; consider restricting in refactor).
- **`cms/fieldslip_import.html`** — Blocks `title`, `content`; no bound form object—relies on `<input type="file" name="import_file">`; view `fieldslip_import` handles POST.
- **`cms/locality_form.html`** — Blocks `title`, `content`; expects `form`; `locality_create`/`locality_edit` functions serve it.
- **`cms/place_form.html`** — Blocks `title`, `content`; expects `form`; `place_create`/`place_edit` functions serve it.
- **`cms/preparation_approve.html`** — Blocks `title`, `content`; expects `form` from `PreparationApproveView` (`LoginRequiredMixin`, curator gate).
- **`cms/preparation_confirm_delete.html`** — Blocks `title`, `content`; expects `preparation` object plus default delete view context; served by `PreparationDeleteView` (login + curator guard).
- **`cms/preparation_form.html`** — Blocks `title`, `content`; expects `form`; used by `PreparationCreateView`/`UpdateView` (login, group-sensitive validation).
- **`cms/preparation_media_upload.html`** — Blocks `title`, `content`; expects `form`, `preparation`; `PreparationMediaUploadView` enforces curator/manager auth before upload.
- **`cms/reference_form.html`** — Blocks `title`, `content`; expects `form`; used by `reference_create`/`reference_edit` (function-based views, typically staff-only via navigation).
- **`cms/storage_form.html`** — Blocks `title`, `content`; expects `form`, `request.path`; served by `StorageCreateView`/`StorageUpdateView` (`LoginRequiredMixin`, `CollectionManagerAccessMixin`).
- **`cms/upload_media.html`** — Blocks `title`, `content`; expects `form`, `accession`; `upload_media` view handles POST (no decorator today—future refactor should enforce auth).

#### QC Wizard Templates
- **`cms/qc/wizard_base.html`** — Blocks `title`, `wizard_title`, `content`, `wizard_heading`, `wizard_subheading`, `wizard_extra_fields`, `wizard_actions`, `extra_scripts`; requires `media`, `accession_form`, `fieldslip_formset`, `row_formset`, `ident_formset`, `specimen_formset`, `reference_formset`, `row_contexts`, `storage_suggestions`, `storage_datalist_id`, `qc_history_logs`, `qc_preview`, `qc_diff`, `form_media`, plus optional `qc_conflicts`, `qc_acknowledged_warnings`.
- **`cms/qc/intern_wizard.html`** — Extends wizard base; fills blocks `wizard_title`, `wizard_heading`, `wizard_subheading`, `wizard_extra_fields`, `wizard_actions`. Requires intern/expert-specific context (`qc_comment`, `qc_comments`, `latest_qc_comment`, `is_expert`, `qc_conflicts`, `qc_diff`).
- **`cms/qc/expert_wizard.html`** — Extends wizard base; similar requirements with expert-only actions (`qc_conflicts`, `qc_comment`, `qc_comments`).
- **`cms/qc/rows_step.html`** — Included by wizard steps; expects `row_formset`, `row_contexts`, `storage_suggestions`, `storage_datalist_id`.
- **`cms/qc/summary_step.html`** — Summaries diff output; requires `qc_diff`, `qc_warnings`/`warnings_map` data from wizard manager.
- **`cms/qc/dashboard_queue.html`** — Partial used by dashboard; expects `qc_sections` (list of dicts with `key`, `label`, `entries`, `has_more`, `action_url_name`, `cta_label`, `empty_message`, `view_all_url`) and optional `qc_extra_links` (label/url pairs).
- **`cms/qc/partials/chip.html`** — Chip component for inline formsets; expects `chip_form`, `chip_type`, `field` iteration, `hidden` flag.
- **`cms/qc/partials/reference_card.html`** — Requires `ref_form` bound fields (`first_author`, `title`, `year`, `page`) plus `hidden` toggle.
- **`cms/qc/partials/row_card.html`** — Requires `row_form`, `display_index`, `row_id`, `hidden`; consumes form field HTML names/IDs for JS ordering.

#### History & Shared Fragments
- **`cms/qc/history.html`** — Blocks `title`, `content`; view `MediaQCHistoryView` (login + role guard) supplies `qc_logs`, optional `filter_media` for heading.
- **`cms/qc/partials/history_list.html`** — Shared log renderer; expects `logs` (iterable of `MediaQCLog`), optional flags `compact`, `show_empty`, plus nested `comments` on each log.
- **`cms/partials/accession_preview_panel.html`** — Partial used on accession detail and QC wizard; expects `accession`, `accession_rows`, `first_identifications`, `taxonomy`, `geologies`, `references`, `media`, `slip` collections, `preview_mode` toggle, and optionally `matched_taxon` metadata.
- **History tables inside detail templates** — `cms/drawerregister_detail.html`, `cms/preparation_detail.html`, and `cms/storage_detail.html` each consume `history_entries` produced by `build_history_entries` and expect entries to expose `.log` (with `history_date`, `history_type`, `history_user`, `history_change_reason`) plus `.changes` iterables for field diffs.

This matrix should be kept in sync with view changes so future refactors can rely on an authoritative source of template dependencies.
