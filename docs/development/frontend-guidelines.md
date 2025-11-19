# CMS Frontend Guidelines

_Last updated: 2025-10-24_

## Overview
The CMS frontend now relies almost entirely on W3.CSS utilities and semantic HTML5 landmarks. Every template extends `base_generic.html`, which loads the W3 stylesheet from the CDN, shared Font Awesome assets, and the small custom override bundle in `app/cms/static/css/style.css`. This document captures the patterns that must be preserved when building or updating templates.

| View Type | Primary Templates | W3.CSS Usage | Local CSS / JS Touchpoints | Notes for Refactor |
| --- | --- | --- | --- | --- |
| List & Search | `cms/*_list.html` variants (accession, drawer, fieldslip, locality, place, preparation, reference, storage) | Shared header rows, filter accordions, and table shells lean on `w3-container`, `w3-row-padding`, `w3-table-all`, and `w3-responsive`.【F:app/cms/templates/cms/accession_list.html†L8-L108】【F:app/cms/templates/cms/reference_list.html†L8-L123】 | Each template embeds a small `toggleAccordion` helper and duplicates the accordion markup; no bespoke CSS classes beyond inherited typography utilities.【F:app/cms/templates/cms/accession_list.html†L24-L109】 | Extract accordion into an include and switch to a shared stimulus/alpine controller to avoid per-template JS duplication. |
| Detail | `cms/*_detail.html` (accession, accession_row, drawerregister, fieldslip, locality, place, preparation, reference, storage) | Cards, summary grids, and related tables now standardise on `<main>/<section>` landmarks, `w3-card`, and Font Awesome section icons for quick scanning.【F:app/cms/templates/cms/accession_detail.html†L1-L135】【F:app/cms/templates/cms/preparation_detail.html†L1-L221】 | Accessions load the `accession_media_preview.js` controller and `.accession-media-hover-preview` styles to support the hover preview while every detail view continues to rely on the shared W3 table shell. | Future enhancements: extract history table rows into a shared include and align curator action buttons with a button helper. |
| Detail + Sub-list | `cms/locality_detail.html`, `cms/storage_detail.html` | Combine W3 cards for the primary object with responsive related-object tables and Font Awesome headings.【F:app/cms/templates/cms/locality_detail.html†L1-L107】 | Manual pagination components mirror the helper used in list templates and rely solely on W3 bar/button classes.【F:app/cms/templates/cms/storage_detail.html†L108-L147】 | Align pagination markup with a single include referenced by both list and detail pages to reduce drift. |
| Dashboard | `cms/dashboard.html`, `cms/qc/dashboard_queue.html` | Role cards now share W3 card wrappers, Font Awesome section icons, and responsive tables with semantic `<section>` landmarks.【F:app/cms/templates/cms/dashboard.html†L1-L240】【F:app/cms/templates/cms/qc/dashboard_queue.html†L1-L74】 | Queue partial still expects context dicts and renders CTA buttons; empty states reuse W3 alert panels. | Future enhancements: extract repeated role-card scaffolding into an include and expose queue metadata via dataclasses to trim template logic. |
| Forms & Wizards | `cms/*_form.html`, `cms/*_wizard*.html`, `cms/add_accession_*` | All forms funnel through the refactored `base_form.html` card which applies W3 classes, ARIA labels, and Font Awesome submit icons; parent templates wrap the include in `<main>` with W3 button links.【F:app/cms/templates/includes/base_form.html†L1-L11】【F:app/cms/templates/includes/base_form_tag.html†L1-L44】【F:app/cms/templates/cms/preparation_form.html†L1-L23】 | Wizard templates continue to add per-step scripts via formset JS includes. | Keep wizard navigation consistent with the shared button styles and audit form-level accessibility when introducing new widgets. |
| History / Audit | `cms/history_table.html`, `cms/history_media_qc_table.html`, `cms/qc/history.html` | Audit tables share the `history_table` partial with `w3-table-all`, `w3-small`, `<time>` stamps, and Font Awesome action icons; the QC history page adds filter controls and pagination.【F:app/cms/templates/cms/history_table.html†L1-L69】【F:app/cms/templates/cms/qc/history.html†L1-L98】 | Detail templates include the partial directly, while the QC list view renders paginated logs via the media-specific helper. | Future enhancements: reuse the QC helper inside wizard previews once legacy CSS is retired. |
| Media / Upload | `cms/preparation_media_upload.html`, `cms/upload_media.html`, `cms/fieldslip_import.html` | All upload flows now render inside W3 cards with shared form markup; the import screen uses standard W3 inputs in place of custom drag/drop styles.【F:app/cms/templates/cms/preparation_media_upload.html†L1-L18】【F:app/cms/templates/cms/fieldslip_import.html†L1-L27】 | No bespoke CSS remains; styling relies purely on W3 utilities. | When adding new uploaders ensure `form.is_multipart` is honoured so the shared include sets `multipart/form-data` automatically. |
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
| Accession detail | `app/cms/templates/cms/accession_detail.html` | Full accession profile with related records. | Embeds the preview panel partial; large screens render a two-tier layout (overview left, specimens/right stack) and include the hover preview assets for media thumbnails.【F:app/cms/templates/cms/accession_detail.html†L1-L138】【F:app/cms/static/cms/js/accession_media_preview.js†L1-L124】 |
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
| Reference form | `app/cms/templates/cms/reference_form.html` | CRUD form for references. | Shares the base W3 form include and Select2 widgets. |
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
| Accession preview panel (partial) | `app/cms/templates/cms/partials/accession_preview_panel.html` | Full preview of accession, field slips, and identifications using stacked W3 cards, semantic sections, and action buttons. | Shared between wizard and detail contexts; honours `preview_mode`, supplies the upper grid layout, and wires media thumbnails with `media-preview-trigger` attributes for the hover controller.【F:app/cms/templates/cms/partials/accession_preview_panel.html†L1-L201】 |

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
| CMS global styles | `app/cms/static/css/style.css` | Flex-aligns the header navigation so the logo, menu links, and auth controls sit on a single row at desktop widths; constrains the logo, resets logout form margin, maintains Select2 width/stacking plus drag handles, and exposes the `.accession-media-hover-preview` helper for enlarged media overlays.【F:app/cms/static/css/style.css†L1-L78】 | Loaded via `base_generic.html` for all CMS pages and public landing. |
| — | — | — | The merge admin and reporting UIs now rely entirely on W3.CSS utilities; dedicated stylesheets were removed in favour of shared markup classes. |

### Redundancy and Consolidation Opportunities
- **Custom CSS scope in `style.css`:** The stylesheet is limited to navigation helpers (`.logo_image`, `.logout-form`, `.sr-only`), Select2 width and stacking overrides, and the drawer drag-handle cursor. Legacy helpers such as `.template_buttons`, `.search-bar`, `.table-container`, and `.template_form_*` remain retired in favour of W3.CSS utilities.【F:app/cms/static/css/style.css†L1-L38】
- **Select2 overrides centralised:** Inline duplication was removed from `base_generic.html`; keep future adjustments inside `style.css` to avoid drift.【F:app/cms/static/css/style.css†L20-L32】【F:app/cms/templates/base_generic.html†L40-L68】
- **Template regression coverage:** Navigation (`test_navigation`), filter widgets (`test_filter_widgets`), and account entrance flows (`test_account_templates`) now assert the presence of W3 classes so future edits cannot silently reintroduce bespoke selectors. Extend this pattern when reworking other templates that lean on W3 utility classes.【F:app/cms/tests/test_navigation.py†L24-L76】【F:app/cms/tests/test_filter_widgets.py†L1-L52】【F:app/cms/tests/test_account_templates.py†L1-L23】

### Follow-up Ideas
- Centralize frequently reused filter accordion markup into an include to reduce duplication across list templates.
- Split the current monolithic `style.css` into domain-specific bundles (public landing, CMS shell, forms, import flows) to simplify future audits.
- Document the expected CSS hooks for dynamically injected components (e.g., Select2, drag handles) within this guideline to aid future refactors.

## Template guidelines

1. **Extend the base layout.** All new templates should inherit from `base_generic.html` to obtain navigation, asset loading, and the responsive grid meta tags.
2. **Use semantic regions.** Continue to wrap primary content in `<main>`, logical sections in `<section>`/`<article>`, and supporting content in `<aside>`/`<footer>`.
3. **Leverage W3 grids before custom CSS.** `w3-row-padding` and `w3-col` (or `w3-half`, `w3-third`, etc.) cover most layout needs. When the design calls for alignment tweaks, prefer W3 spacing utilities (`w3-margin`, `w3-padding`) over hand-written rules.
4. **Buttons and links.** Use `w3-button` combined with palette classes (`w3-theme`, `w3-teal`, `w3-white`, `w3-border`) for all calls to action. Rounded buttons should add `w3-round` or `w3-round-large` instead of bespoke border radii.
5. **Forms.** Django form widgets should receive W3 classes via either the shared base form include or widget `attrs`. Inputs use `w3-input`, selects use `w3-select`, and groups should sit inside `w3-section` or `w3-margin-bottom` containers. Preserve ARIA attributes and label associations provided by Django.
6. **Tables.** Data tables should combine `w3-table-all` with `w3-striped`, `w3-hoverable`, and `w3-responsive` as appropriate. Pagination controls reuse the navigation button pattern with `w3-bar` wrappers.
7. **Messages and alerts.** Use W3 panel helpers (`w3-panel`, `w3-pale-green`, `w3-border`) for flash messages, validation summaries, or background highlights.
8. **Icons.** Font Awesome 6 is available globally. Use the standard `<i class="fa-solid fa-icon">` markup and avoid inline SVG unless the icon is missing from FA.

## Custom CSS inventory
The shared stylesheet `app/cms/static/css/style.css` intentionally remains small. Only the following helpers are allowed:

- `.site-navigation`, `.nav-items`, `.nav-link`, `.nav-user-label`, `.nav-auth`, `.nav-dropdown` – convert the W3 bar into a flex toolbar so the logo, links, and auth controls remain on one row on larger screens while preserving mobile stacking.
- `.logo_image` – constrains the navigation logo width so it fits within the bar.
- `.logout-form` – removes default margins around the logout button’s form wrapper so it aligns with bar items.
- `.sr-only` – provides an accessible screen-reader-only helper that W3.CSS does not supply.
- `.django-select2`, `.select2-container`, `.select2-selection`, `.select2-dropdown` – ensure Select2 widgets span full width and stack above modals or dropdowns.
- `.drag-handle` – keeps the grab cursor for drag-to-reorder handles; JavaScript toggles this on drawer lists.
- `.accession-media-hover-preview` – fixed-position container for enlarged accession media previews, toggled by the dedicated JS controller.

Do not add new selectors without first checking whether a W3 utility or an existing helper can cover the requirement. If a new override is unavoidable, document the rationale directly above the rule and update this guideline.

## JavaScript expectations
Certain scripts assume W3 classes are present:

- `static/javascript.js` toggles `w3-show` and `w3-hide` to open the mobile navigation panel.
- `static/js/merge_admin.js` generates search results using `w3-card-4`, `w3-padding`, and `w3-button` classes. Any markup changes must update both the template and script.
- Inventory scanning scripts add contextual classes such as `w3-pale-green` to status elements. Keep those hooks stable.
- `static/cms/js/accession_media_preview.js` looks for `.media-preview-trigger` elements with `data-media-preview` and `data-media-alt` attributes and toggles the `#media-hover-preview` container. Maintain these hooks when adjusting the media table markup.【F:app/cms/static/cms/js/accession_media_preview.js†L20-L124】

## Testing coverage
Template regression tests live in `app/cms/tests/` and verify that W3 classes render as expected:

- `test_navigation.py` asserts the navigation bar structure and mobile toggle behaviour.
- `test_filter_widgets.py` ensures django-filter widgets expose W3 form classes.
- `test_account_templates.py` checks the login and signup templates for the expected card and button classes.

Add similar assertions when creating new templates that depend on W3-specific structure.

## Future enhancements
- Extract the repeated filter accordion into a reusable include to reduce duplication across list templates.
- Publish example snippets for common layouts (cards, tables, modals) so contributors can copy the sanctioned markup.
- Audit remaining JavaScript-driven DOM injections to ensure they emit the same class names as the server-rendered templates.
