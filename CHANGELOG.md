# Changelog

## Unreleased
- Automate dependency snapshots in the development planning and coding prompts via `docs/scripts/update_prompts.py`, including supporting tests and maintenance docs (T3).
- Document geological time support across locality workflows, including admin import/export guidance, printable reporting expectations, and pytest coverage notes (T3).
- Standardise CMS list and detail templates on semantic W3.CSS layouts, refreshed Font Awesome icons, and updated template tests; document the patterns in user and developer guides (T2).
- Document the accession detail layout restructure and hover media preview workflow across user, admin, and developer guides (T5).
- Capture the accession detail QA checklist, coverage command, and rollout/rollback guidance following the layout restructure (T6).
- Document the accession row print card workflow, including taxonomy fallback handling, print controls, and permission parity with edit actions, in the user guide (T6).
- Expand CMS template audit with W3.CSS layout dependency summary and upload-view gaps in `docs/dev/frontend-guidelines.md` (T1).
- Add end-user, admin, and developer documentation for the NOW taxonomy sync workflow and record the feature in the changelog (T5).
- Refactor CMS form templates and dashboards to share the W3.CSS base form card, refreshed role tiles, and accessibility-focused regression tests; update user/admin/dev guides accordingly (T3).
- Standardise django-simple-history tables and the Media QC history page on shared W3.CSS partials with filter controls, pagination, and documentation updates (T4).
- Refresh the primary navigation with a flex-aligned W3.CSS toolbar so the logo, links, and auth controls share one desktop row, reuse consistent nav button styling, and update developer docs plus template regression tests (T1).
- Adopt W3.CSS styling for list filters, inventory session controls, and report layouts, trim legacy selectors from `style.css`, expand developer docs, and add widget-class regression tests.
- Convert the admin merge workflow and reporting dashboards to W3.CSS-only markup, drop bespoke CSS bundles, refresh merge tooling JS, and document the new patterns.
- Consolidate residual custom CSS to navigation, Select2, and drag-handle helpers while migrating account entrance flows to W3.CSS cards and backfill template tests plus docs covering the W3 regression expectations.
