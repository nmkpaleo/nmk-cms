# Changelog

## Unreleased
- Update accession detail pages to hide Comments from anonymous visitors while hyperlinking reference titles; adjust locality
  detail heading to show “Associated published accessions” for unauthenticated users while retaining the existing heading for
  signed-in users (template regression tests added).
- Document manual QC import taxonomy mapping so `taxon_verbatim` captures the lowest supplied taxon and qualifiers from upload spreadsheets.
- Document that the dashboard disables the Create single accession action when a collection manager lacks an active accession number series, while leaving the Generate batch shortcut unchanged.
- Document the dashboard Generate batch shortcut for accession number series, including access rules for collection managers and the self-service workflow that redirects to the accession wizard once numbers are reserved.
- Record the accession wizard update that shows specimen numbers as display-only text while preserving the selected value through submission.
- Fix Drawer Register edit form taxonomy queryset errors and surface Locality/Taxon cards on the drawer detail page; update user/admin guidance accordingly (CMS-001, CMS-003, CMS-005).
- Document the unified identification taxonomy workflow, including cleaned vs verbatim taxon fields, automatic controlled-record linking, and rollback steps for the migration (CMS-TAX-UNIFY).
- Automate dependency snapshots in the development planning and coding prompts via `docs/scripts/update_prompts.py`, including supporting tests and maintenance docs (T3).
- Document Drawer Register admin export behavior to clarify that taxa values use the primary taxon name (T3.2).
- Document geological time support across locality workflows, including admin import/export guidance, printable reporting expectations, and pytest coverage notes (T3).
- Standardise CMS list and detail templates on semantic W3.CSS layouts, refreshed Font Awesome icons, and updated template tests; document the patterns in user and developer guides (T2).
- Document the accession detail layout restructure and hover media preview workflow across user, admin, and developer guides (T5).
- Record the accession field slip modal overlay fix, including accessibility updates to close Select2 dropdowns and hide background content while the dialog is open (CMS-ACC-UI-004).
- Capture the accession detail QA checklist, coverage command, and rollout/rollback guidance following the layout restructure (T6).
- Document the accession row print card workflow, including taxonomy fallback handling, print controls, and permission parity with edit actions, in the user guide (T6).
- Add QR codes to accession row print cards (big and small) so printouts link back to the specimen detail page, rendered
  server-side with the django-qr-code integration and paired with in-page print controls.
- Add a reusable Field Slip related accessions section and document the visibility rules for collection managers and superusers (T4).
- Expand CMS template audit with W3.CSS layout dependency summary and upload-view gaps in `docs/development/frontend-guidelines.md` (T1).
- Add end-user, admin, and developer documentation for the NOW taxonomy sync workflow and record the feature in the changelog (T5).
- Refactor CMS form templates and dashboards to share the W3.CSS base form card, refreshed role tiles, and accessibility-focused regression tests; update user/admin/dev guides accordingly (T3).
- Standardise django-simple-history tables and the Media QC history page on shared W3.CSS partials with filter controls, pagination, and documentation updates (T4).
- Refresh the primary navigation with a flex-aligned W3.CSS toolbar so the logo, links, and auth controls share one desktop row, reuse consistent nav button styling, and update developer docs plus template regression tests (T1).
- Adopt W3.CSS styling for list filters, inventory session controls, and report layouts, trim legacy selectors from `style.css`, expand developer docs, and add widget-class regression tests.
- Convert the admin merge workflow and reporting dashboards to W3.CSS-only markup, drop bespoke CSS bundles, refresh merge tooling JS, and document the new patterns.
- Consolidate residual custom CSS to navigation, Select2, and drag-handle helpers while migrating account entrance flows to W3.CSS cards and backfill template tests plus docs covering the W3 regression expectations.
- Add regression tests for the refreshed allauth templates (including ORCID CTA and skull hero) and document the W3.CSS requirements across user, admin, and developer guides (T6).
- Document FieldSlip merge deduplication, including admin messaging and developer guidance for relation conflict handling, and update merge-tool docs accordingly (T5).
- Record FieldSlip merge QA execution results, lint/test observations, and rollout guidance for operations teams (T6).
- Document the expert QC reference delete control, including save behavior and rollback expectations (T5).
- Document the tabbed Change log UI for drawer and storage details, including user/admin guidance and updated development audit notes.
- Add user, admin, and developer guidance for the FIELD_SELECTION merge workflow covering Field Slip, Storage, and Reference merges plus the dedicated field-selection view.
- Document the admin and field-selection multi-merge workflow so all selected candidates merge into the chosen target sequentially with per-field strategies preserved.
