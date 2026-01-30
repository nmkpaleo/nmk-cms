# Specimen List PDF Ingestion Plan

## 1️⃣ Assumptions & Scope
- Django 5.2 with MySQL; background work executed via existing async/task mechanism (e.g., management command, Celery, or in-app job runner already used in the project).
- Primary implementation lives in the existing `cms` app; no new Django app unless a later architecture review indicates otherwise.
- OCR/classification pipelines should reuse existing OCR or scanning utilities already in the codebase; only add net-new services where gaps are confirmed.
- Storage uses Django `FileField` with UUID-based naming for stored files while retaining original filenames in the database.
- No new Python packages are strictly required for the ingestion foundation: rely on existing Pillow and system-level PDF tooling (poppler-utils) for page splitting. Add a Python wrapper (e.g., `pdf2image`) only if project standards require a pure-Python interface.
- Initial scope focuses on **file format & ingestion strategy**: PDF upload, page-splitting pipeline, provenance metadata, and database persistence. OCR and extraction flows remain stubbed for later phases.

**Apps to modify or create**
- **Modify:** `app/cms` (models, admin, forms, views, background tasks, utilities), `app/templates` (shared templates), `docs` (planning + ops guidance), `tests` (pytest suites for ingestion flow).
- **No new app planned** unless needed for task isolation once the review stage and AI pipelines expand.

**Reused vs. new components**
- **Reuse:** existing import logic, OCR utilities, and any current upload processing helpers.
- **New:** `SpecimenListPDF` + `SpecimenListPage` models, ingestion services for PDF splitting, upload forms and admin actions, and reviewer lock utilities.

**Required packages**
- **No new Python deps required** initially; use Pillow and OS-level poppler-utils for `pdftoppm`/`pdfinfo`.
- If system tooling is unavailable in deployment containers, propose adding a single wrapper package (e.g., `pdf2image`) after validating platform compatibility and security review.

## 2️⃣ High-Level Plan (5–12 steps)
1. **Data model & migrations**: Add `SpecimenListPDF` and `SpecimenListPage` models with UUID file storage, status fields, and `django-simple-history` tracking; include dedupe fields (sha256) and reviewer locking metadata.
2. **Storage + upload flow**: Implement `SourceLabel` normalization (enum or model) and an upload form that captures a source label and accepts multiple PDFs; persist original filenames and UUID-only stored names.
3. **Background splitting pipeline**: Add a service layer that saves original PDFs, triggers page splitting (300–400 DPI PNGs), computes sha256, and creates `SpecimenListPage` rows; ensure idempotency and resumability on failures.
4. **Views, URLs & CBVs**: Add class-based views for upload, PDF detail, and page list/review queues; ensure authenticated access and reviewer role gating via permissions.
5. **Templates & UI**: Extend `base_generic.html` with semantic HTML5 landmarks, W3.CSS layout, and Font Awesome icons; ensure mobile-first layout and page-by-page review controls (no edit collisions, lock indicators).
6. **Filtering & pagination**: Use `django-filter` for lists by status/source label/assignee; add pagination for PDFs and pages for performance.
7. **Admin integration**: Register models in Django admin with list filters, readonly metadata, and inline pages; include admin action to re-run splitting for failed PDFs.
8. **Audit trail**: Integrate `django-simple-history` for both models and capture uploader, reviewer, and state transitions; ensure structured logging for background jobs.
9. **Testing strategy**: Add pytest/pytest-django tests for model constraints, upload flow, pipeline idempotency, and locking behavior; enforce coverage ≥ 90% for new code and migrations checks.
10. **Docs & changelog**: Update `/docs/user`, `/docs/admin`, `/docs/development`, and `CHANGELOG.md` with ingestion workflow, permissions, and operational notes (no internal code citations). Align PR messaging to current scope with each commit.
11. **Rollout & feature flags**: Add feature flag (settings-based) to gate the ingestion UI; document rollback by disabling flag and preserving files; ensure migrations are reversible.

**PR messaging note**: Each commit should update the PR title/summary to reflect the latest scope (e.g., “Ingestion models + upload workflow” → “Add PDF splitting pipeline & reviewer locks” as scope expands).

**Testing/CI expectations**: Use pytest/pytest-django for unit/integration coverage ≥ 90%, include `python manage.py makemigrations --check` and `python manage.py migrate --check`, run linting/type checks if configured, and run docs validation steps that do not require MkDocs.

## 3️⃣ Tasks (JSON)
[
  {
    "id": "T1",
    "title": "Add specimen list ingestion models",
    "summary": "Create SpecimenListPDF and SpecimenListPage models with history tracking, UUID-based file storage, and status fields aligned to ingestion states.",
    "app": "apps.cms",
    "files_touched": [
      "app/cms/models.py",
      "app/cms/migrations/XXXX_specimen_list_models.py"
    ],
    "migrations": true,
    "settings_changes": [
      "MEDIA_ROOT storage path additions for specimen list uploads",
      "Feature flag setting for ingestion UI gating"
    ],
    "packages": [],
    "permissions": [
      "cms.add_specimenlistpdf",
      "cms.change_specimenlistpage",
      "cms.review_specimenlistpage"
    ],
    "acceptance_criteria": [
      "Models persist upload metadata, source label, status, and page metadata without collisions.",
      "History tables capture create/update events for audit.",
      "UUID-based filenames are stored while preserving original filenames in DB."
    ],
    "test_plan": [
      "pytest: model validation tests (status enums, unique constraints, history tracking)."
    ],
    "docs_touched": [
      "docs/development/specimen_list_ingestion_plan.md"
    ],
    "dependencies": [],
    "estimate_hours": 6.0,
    "risk_level": "medium",
    "priority": "high",
    "reviewer_notes": [
      "Confirm file storage paths align with existing MEDIA_ROOT conventions."
    ]
  },
  {
    "id": "T2",
    "title": "Build upload UI and ingestion pipeline",
    "summary": "Add forms, views, and background pipeline for PDF upload, sha256 computation, and page-splitting into PNGs with page metadata rows.",
    "app": "apps.cms",
    "files_touched": [
      "app/cms/forms.py",
      "app/cms/views.py",
      "app/cms/urls.py",
      "app/cms/upload_processing.py",
      "app/templates/cms/specimen_list_upload.html"
    ],
    "migrations": false,
    "settings_changes": [
      "Background task configuration if required (queue name, timeout)"
    ],
    "packages": [],
    "permissions": [
      "cms.add_specimenlistpdf"
    ],
    "acceptance_criteria": [
      "Users can upload multiple PDFs with a required source label.",
      "Original PDFs are stored by UUID, with original filenames preserved in the DB.",
      "Page images and metadata rows are created asynchronously and update PDF status."
    ],
    "test_plan": [
      "pytest: integration tests for upload form validation and pipeline idempotency.",
      "pytest: mocks for PDF splitting utilities and sha256 checksum calculation."
    ],
    "docs_touched": [
      "docs/user/specimen_list_ingestion.md",
      "docs/admin/specimen_list_ingestion.md"
    ],
    "dependencies": [
      "T1"
    ],
    "estimate_hours": 12.0,
    "risk_level": "high",
    "priority": "high",
    "reviewer_notes": [
      "Ensure page splitting uses deterministic naming and safe temp directories."
    ]
  },
  {
    "id": "T3",
    "title": "Implement review queues and locking",
    "summary": "Create reviewer queues, locking logic, and page list views with filters and pagination to avoid review collisions.",
    "app": "apps.cms",
    "files_touched": [
      "app/cms/views.py",
      "app/cms/filters.py",
      "app/cms/templates/cms/specimen_list_queue.html",
      "app/cms/templates/cms/specimen_list_page_review.html"
    ],
    "migrations": false,
    "settings_changes": [
      "Lock TTL configuration for page review"
    ],
    "packages": [],
    "permissions": [
      "cms.review_specimenlistpage"
    ],
    "acceptance_criteria": [
      "Reviewers can claim/lock pages without collisions and release or timeout locks.",
      "Queue views support filtering by status, source label, and assignee.",
      "Templates are mobile-first with semantic landmarks and accessible controls."
    ],
    "test_plan": [
      "pytest: queue filtering and lock acquisition/release behavior tests.",
      "pytest: permission and access control tests for reviewer flows."
    ],
    "docs_touched": [
      "docs/user/specimen_list_review.md"
    ],
    "dependencies": [
      "T1",
      "T2"
    ],
    "estimate_hours": 10.0,
    "risk_level": "medium",
    "priority": "medium",
    "reviewer_notes": [
      "Define clear lock takeover rules to avoid deadlocks."
    ]
  },
  {
    "id": "T4",
    "title": "Admin + audit trail hardening",
    "summary": "Register models in admin, wire django-simple-history, and add operational safeguards for pipeline errors.",
    "app": "apps.cms",
    "files_touched": [
      "app/cms/admin.py",
      "app/cms/models.py",
      "app/cms/templates/admin/specimen_list_pdf.html"
    ],
    "migrations": false,
    "settings_changes": [],
    "packages": [],
    "permissions": [
      "cms.view_specimenlistpdf",
      "cms.view_specimenlistpage"
    ],
    "acceptance_criteria": [
      "Admin list views surface ingestion status, page counts, and errors.",
      "History entries capture reviewer actions and status transitions.",
      "Admins can requeue or re-run splitting for failed PDFs."
    ],
    "test_plan": [
      "pytest: admin views render with expected fields and permissions."
    ],
    "docs_touched": [
      "docs/admin/specimen_list_ingestion.md",
      "CHANGELOG.md"
    ],
    "dependencies": [
      "T1",
      "T2"
    ],
    "estimate_hours": 6.0,
    "risk_level": "low",
    "priority": "medium",
    "reviewer_notes": []
  },
  {
    "id": "T5",
    "title": "Docs and rollout checklist",
    "summary": "Document ingestion workflow, operational runbooks, and rollout/rollback steps for the new pipeline.",
    "app": "docs",
    "files_touched": [
      "docs/user/specimen_list_ingestion.md",
      "docs/user/specimen_list_review.md",
      "docs/admin/specimen_list_ingestion.md",
      "docs/development/specimen_list_ingestion_plan.md",
      "CHANGELOG.md"
    ],
    "migrations": false,
    "settings_changes": [],
    "packages": [],
    "permissions": [],
    "acceptance_criteria": [
      "Docs describe upload requirements, reviewer flow, and admin troubleshooting without internal code citations.",
      "Rollout/rollback steps are explicit and align with feature-flag usage."
    ],
    "test_plan": [
      "Docs lint/build steps executed without MkDocs."
    ],
    "docs_touched": [
      "docs/user/specimen_list_ingestion.md",
      "docs/user/specimen_list_review.md",
      "docs/admin/specimen_list_ingestion.md",
      "docs/development/specimen_list_ingestion_plan.md",
      "CHANGELOG.md"
    ],
    "dependencies": [
      "T1",
      "T2",
      "T3",
      "T4"
    ],
    "estimate_hours": 4.0,
    "risk_level": "low",
    "priority": "low",
    "reviewer_notes": []
  }
]

## 4️⃣ Risks & Mitigations
- **Auth flows**: Restrict ingestion and review to authenticated users with explicit permissions; add audit trail entries for reviewer actions.
- **Data migrations**: Use reversible migrations with explicit defaults for new status fields; add backfill data migrations only if required.
- **Data loss prevention**: Retain original PDFs permanently (or per retention policy) and keep page images immutable; store sha256 hashes to detect duplicates.
- **Performance**: Run PDF splitting in background jobs, throttle queue concurrency, and index by source label/status for list views.
- **Accessibility**: Enforce WCAG AA in templates, include clear focus states, ARIA labels for review controls, and keyboard navigation.
- **Localization**: Wrap UI strings in gettext and avoid hard-coded dates; ensure locale-aware formatting.
- **Dependency vulnerabilities**: Avoid new deps; if adding a PDF tool, vet versions and pin ranges.
- **Rollback strategy**: Disable feature flag to hide UI, keep stored files intact, and allow reprocessing later; migration rollback should be safe.

## 5️⃣ Out-of-Scope
- OCR model selection, AI-assisted column detection, and extraction logic.
- Downstream accession row creation, validation, and import workflows.
- Full reviewer analytics dashboard and SLA reporting.
- Automated classification of page type beyond basic scaffolding.

## 6️⃣ Definition of Done ✅
- Acceptance criteria for ingestion foundation are met.
- Unit/integration tests pass with ≥90% coverage for new code.
- Migrations applied (if any) and reversible.
- Admin integration available with history tracking via django-simple-history.
- django-filter used for queue/list filtering.
- Templates are mobile-first with semantic HTML5 landmarks and W3.CSS styling.
- i18n strings wrapped for localization.
- Requirements changes (if any) are justified and documented.
- Docs updated in `/docs/user`, `/docs/admin`, `/docs/development`, and `CHANGELOG.md`.
- CI green and staging verified.
- Feature demoed to stakeholders.
- Rollback plan confirmed and documented.
