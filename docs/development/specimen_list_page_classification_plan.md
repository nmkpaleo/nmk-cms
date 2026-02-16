# Specimen List Page Classification Plan

## 1️⃣ Assumptions & Scope
- Django 5.2 with MySQL; background processing follows the existing OCR queue or task runner patterns already used for scans.
- The existing OCR pipeline in the `cms` app will be extended rather than introducing a new Django app.
- Page images already exist from the PDF splitting workflow, and classification runs **before** row extraction.
- Use current OpenAI integration (`openai` dependency is already available) and existing OCR utilities for image handling; no new external packages are required unless the current pipeline lacks a lightweight classification hook.
- Classification results are stored as structured metadata (JSON) on the page model with status and confidence; raw OCR text is stored only for pages routed to “searchable text.”
- Classification can be toggled via a settings-based feature flag to support staged rollout and rollback.

**Apps to modify or create**
- **Modify:** `app/cms` (models, OCR/classification utilities, background tasks, admin, views), `app/templates` (queue UI), `docs` (planning + ops guidance), `tests` (pytest suites for classification flow).
- **No new app planned**; reuse the current OCR pipeline in `cms`.

**Reused vs. new components**
- **Reuse:** existing OCR request helpers, OpenAI usage logging, admin OCR queue patterns, and media QC logging where applicable.
- **New:** page-level classification workflow, status fields/enums, lightweight prompt template for page type, and UI routing for downstream extraction.

**Required packages**
- **No new Python deps required**; rely on existing `openai` SDK and image handling tooling already in the repository.

## 2️⃣ High-Level Plan (5–12 steps)
1. **Model updates & migrations**: Extend the specimen list page model with classification status, page type enum (`specimen_list_details`, `specimen_list_relations`, `handwritten_text`, `typewritten_text`, `other`), confidence, and notes; add django-simple-history tracking for classification changes.
2. **Classification service layer**: Add a small service in the existing OCR utility module to submit page images to OpenAI with the lightweight prompt and return a structured JSON response; align with existing OCR retry/timeout behavior and usage logging.
3. **Queue integration**: Add a background task (or management command hook) to classify pending pages in batches, respecting existing OCR throttling/quota rules; ensure idempotency and resumability.
4. **Views, URLs & CBVs**: Add class-based views for classification status dashboards and queue actions; restrict access via permissions similar to existing OCR/admin actions.
5. **Templates & UI routing**: Extend `base_generic.html` with semantic HTML5 landmarks, W3.CSS, and Font Awesome to present classification status; route `specimen_list` pages to row extraction UI and others to searchable OCR text view.
6. **Filtering & pagination**: Use `django-filter` and pagination on page lists by classification status, confidence thresholds, source label, and assignee.
7. **Admin integration**: Update admin with list filters, readonly classification metadata, and bulk actions to re-queue classification or clear results.
8. **Audit trail**: Capture classification state changes in history and log LLM usage in existing usage tracking tables for cost auditing.
9. **Testing strategy**: Add pytest/pytest-django tests for classification responses, status transitions, permissioned access to queues, and failure handling (timeouts/quota exhaustion).
10. **Docs & changelog**: Update `/docs/user`, `/docs/admin`, `/docs/development`, and `CHANGELOG.md` with classification workflow, queue ops guidance, and routing behavior (no internal code citations).
11. **Rollout & feature flags**: Add a settings-based feature flag to enable classification; document rollback by disabling the flag and leaving stored results intact.

**PR messaging note**: As scope evolves across commits (models → service layer → UI), update PR title/body to reflect the latest additions and avoid stale summaries.

**Testing/CI expectations**: Use pytest/pytest-django with coverage ≥ 90%, run `python manage.py makemigrations --check` and `python manage.py migrate --check`, execute lint/type checks if configured, and run docs verification steps that do not require MkDocs.

## 3️⃣ Tasks (JSON)
[
  {
    "id": "T1",
    "title": "Add page classification fields",
    "summary": "Extend specimen list page model with classification status, page type enum, confidence, and notes, including history tracking.",
    "app": "apps.cms",
    "files_touched": [
      "app/cms/models.py",
      "app/cms/migrations/XXXX_specimen_list_page_classification.py"
    ],
    "migrations": true,
    "settings_changes": [
      "Feature flag to enable page classification workflow"
    ],
    "packages": [],
    "permissions": [
      "cms.change_specimenlistpage",
      "cms.review_specimenlistpage"
    ],
    "acceptance_criteria": [
      "Classification metadata can be stored per page with validated enum values.",
      "History tracking captures classification updates."
    ],
    "test_plan": [
      "pytest: model validation tests for status enum, confidence bounds, and history tracking."
    ],
    "docs_touched": [
      "docs/development/specimen_list_page_classification_plan.md"
    ],
    "dependencies": [],
    "estimate_hours": 5.0,
    "risk_level": "low",
    "priority": "high",
    "reviewer_notes": [
      "Confirm enum naming matches downstream routing expectations."
    ]
  },
  {
    "id": "T2",
    "title": "Implement classification service",
    "summary": "Create a lightweight OCR/LLM classification prompt for specimen list pages and integrate with existing OpenAI usage logging.",
    "app": "apps.cms",
    "files_touched": [
      "app/cms/ocr_processing.py",
      "app/cms/llm_usage.py"
    ],
    "migrations": false,
    "settings_changes": [
      "Optional: classification timeout or retry settings"
    ],
    "packages": [],
    "permissions": [
      "cms.change_specimenlistpage"
    ],
    "acceptance_criteria": [
      "Classification returns structured JSON with page_type, confidence, and notes.",
      "Usage and latency are recorded alongside other OCR requests."
    ],
    "test_plan": [
      "pytest: unit tests with mocked OpenAI responses and failure handling (timeouts/quota)."
    ],
    "docs_touched": [
      "docs/development/specimen_list_page_classification_plan.md"
    ],
    "dependencies": [
      "T1"
    ],
    "estimate_hours": 8.0,
    "risk_level": "medium",
    "priority": "high",
    "reviewer_notes": [
      "Ensure prompt is concise and consistent with OCR pipeline conventions."
    ]
  },
  {
    "id": "T3",
    "title": "Add classification queue processing",
    "summary": "Batch-classify pending specimen list pages with idempotent updates and retry controls aligned to existing OCR queues.",
    "app": "apps.cms",
    "files_touched": [
      "app/cms/management/commands/classify_specimen_pages.py",
      "app/cms/tasks.py"
    ],
    "migrations": false,
    "settings_changes": [
      "Queue concurrency settings or batch size configuration"
    ],
    "packages": [],
    "permissions": [
      "cms.review_specimenlistpage"
    ],
    "acceptance_criteria": [
      "Classification queue updates pages without duplicate processing.",
      "Failures are captured with retry metadata and surfaced in logs."
    ],
    "test_plan": [
      "pytest: queue processing integration tests with mocked classification service."
    ],
    "docs_touched": [
      "docs/admin/specimen_list_classification.md"
    ],
    "dependencies": [
      "T1",
      "T2"
    ],
    "estimate_hours": 10.0,
    "risk_level": "medium",
    "priority": "medium",
    "reviewer_notes": [
      "Align batch processing with existing OCR admin queue patterns."
    ]
  },
  {
    "id": "T4",
    "title": "UI routing and filters",
    "summary": "Expose classification status in list/review UI, route specimen_list pages to row extraction, and add filters/pagination.",
    "app": "apps.cms",
    "files_touched": [
      "app/cms/views.py",
      "app/cms/filters.py",
      "app/templates/cms/specimen_list_queue.html",
      "app/templates/cms/specimen_list_page_detail.html"
    ],
    "migrations": false,
    "settings_changes": [],
    "packages": [],
    "permissions": [
      "cms.review_specimenlistpage"
    ],
    "acceptance_criteria": [
      "Queue UI displays classification status and confidence.",
      "Non-specimen pages are routed to searchable OCR text-only views."
    ],
    "test_plan": [
      "pytest: view tests for filtering, pagination, and permission checks."
    ],
    "docs_touched": [
      "docs/user/specimen_list_classification.md"
    ],
    "dependencies": [
      "T1",
      "T2",
      "T3"
    ],
    "estimate_hours": 9.0,
    "risk_level": "medium",
    "priority": "medium",
    "reviewer_notes": [
      "Ensure templates include semantic HTML5 landmarks and mobile-first layout."
    ]
  },
  {
    "id": "T5",
    "title": "Admin & audit trail enhancements",
    "summary": "Update admin to surface classification metadata, add bulk actions, and ensure history logs cover classification changes.",
    "app": "apps.cms",
    "files_touched": [
      "app/cms/admin.py",
      "app/cms/models.py"
    ],
    "migrations": false,
    "settings_changes": [],
    "packages": [],
    "permissions": [
      "cms.view_specimenlistpage",
      "cms.change_specimenlistpage"
    ],
    "acceptance_criteria": [
      "Admins can view and re-queue classification from list/detail views.",
      "History logs capture classification status updates."
    ],
    "test_plan": [
      "pytest: admin view rendering and action tests."
    ],
    "docs_touched": [
      "docs/admin/specimen_list_classification.md",
      "CHANGELOG.md"
    ],
    "dependencies": [
      "T1",
      "T2"
    ],
    "estimate_hours": 6.0,
    "risk_level": "low",
    "priority": "low",
    "reviewer_notes": []
  },
  {
    "id": "T6",
    "title": "Documentation and rollout guidance",
    "summary": "Document classification workflow, operational runbooks, and rollback steps for the new page routing behavior.",
    "app": "docs",
    "files_touched": [
      "docs/user/specimen_list_classification.md",
      "docs/admin/specimen_list_classification.md",
      "docs/development/specimen_list_page_classification_plan.md",
      "CHANGELOG.md"
    ],
    "migrations": false,
    "settings_changes": [],
    "packages": [],
    "permissions": [],
    "acceptance_criteria": [
      "Docs cover classification states, queue operations, and routing behaviors without internal code citations.",
      "Rollback steps are explicit and reference the feature flag."
    ],
    "test_plan": [
      "Docs lint/build steps executed without MkDocs."
    ],
    "docs_touched": [
      "docs/user/specimen_list_classification.md",
      "docs/admin/specimen_list_classification.md",
      "docs/development/specimen_list_page_classification_plan.md",
      "CHANGELOG.md"
    ],
    "dependencies": [
      "T1",
      "T2",
      "T3",
      "T4",
      "T5"
    ],
    "estimate_hours": 4.0,
    "risk_level": "low",
    "priority": "low",
    "reviewer_notes": []
  }
]

## 4️⃣ Risks & Mitigations
- **Auth flows**: Gate classification and queue actions behind existing OCR/admin permissions; log all actions for audit.
- **Data migrations**: Add reversible migrations for new fields; avoid backfilling unless necessary.
- **Data loss prevention**: Keep original page images immutable; store classification payloads separately from raw OCR text.
- **Performance**: Batch classification with throttling; cache results to avoid re-processing.
- **Accessibility**: Ensure queue templates follow WCAG AA, include keyboard navigation, and clear focus states.
- **Localization**: Wrap user-facing strings in gettext and use locale-aware formatting.
- **Dependency vulnerabilities**: Avoid new dependencies; monitor OpenAI SDK updates and pin if needed.
- **Rollback strategy**: Disable the feature flag to stop classification; preserve stored results and allow reprocessing after re-enable.

## 5️⃣ Out-of-Scope
- Row extraction and downstream accession creation workflows.
- Training or fine-tuning custom OCR models.
- Full analytics dashboards for classification accuracy.
- Automated correction or human-in-the-loop review UI beyond basic routing.

## 6️⃣ Definition of Done ✅
- Acceptance criteria for page classification are met.
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
