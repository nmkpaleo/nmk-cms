# CMS Template and CSS Inventory

_Last updated: 2025-10-14_

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
| Accession preview panel (partial) | `app/cms/templates/cms/partials/accession_preview_panel.html` | Full preview of accession, field slips, and identifications. | Shared between wizard and detail contexts. |

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
