# Specimen Page Approval Media Location Sync — Implementation Plan

## 1️⃣ Assumptions & Scope

### Django-specific assumptions
- The `/specimen-lists/pages/<id>/review/` endpoint is implemented in an existing app under `apps/` and already contains the "Approve page" action handler (likely a CBV `post()` or a function view).
- A `Media` model already persists file-path metadata (e.g., `file`, `path`, or equivalent) and is related to the scanned page or scan artifact being moved during approval.
- File movement currently happens through Django storage (`FileField.storage`) or `os/shutil`; either way, final source-of-truth should become the `Media` model path saved in DB.
- Database is MySQL (`mysqlclient`) and app uses Django 5.2.11; migration strategy must stay MySQL-safe (avoid non-portable SQL and backend-specific assertions in tests).
- `django-simple-history` is active and expected to capture path/location field updates for auditability.
- Current-user attribution for save hooks may depend on CRUM (`django-crum`) and/or custom middleware; tests must initialize user context where model validation/save hooks require it.

### Apps to modify or create
- **Modify (expected)**: existing specimen list/page review app in `apps/<existing_app>/`.
- **Modify (expected)**: shared media/domain app in `apps/<media_or_assets_app>/` containing `Media` model and admin.
- **Modify (expected)**: templates under `templates/` only if UI confirmation/error messaging changes.
- **Create**: no new app unless ownership boundaries are currently broken; prefer extending existing domain modules.

### Reused vs. new models/forms/views
- **Reuse**:
  - Existing review view/action endpoint.
  - Existing `Media` model and relation graph.
  - Existing permission checks and approval workflow services.
- **New (minimal)**:
  - A small domain service/helper method (e.g., `sync_media_location_after_move`) to centralize move+DB update atomically.
  - Optional lightweight audit/event method if existing logging is insufficient.
- **Avoid**:
  - New model unless missing persistent fields for location state.
  - Duplicate move logic scattered across views/tasks.

### Required packages (justify)
- **No new dependency required** (preferred).
- Use already-installed stack:
  - Django storage APIs in Django 5.2.11 for backend-agnostic path updates.
  - `django-simple-history` for file-location change auditing.
  - `pytest-django` for regression coverage.
- If future async offloading is needed, defer and evaluate existing infra before adding queue dependencies.

## 2️⃣ High-Level Plan (5–12 steps)

1. **Map current approval flow and file move call path**  
   Trace the approve action from URL/view to service/util that moves the scan image; identify exact write points for the `Media` record and where drift can occur.

2. **Define single source of truth for media location**  
   Standardize on one canonical field in `Media` (e.g., storage-relative file path). If multiple fields exist, mark one authoritative and deprecate write duplication (DRY).

3. **Implement atomic move-and-sync service boundary**  
   Introduce/refactor to a reusable domain service in `apps/<app>/services.py` that:
   - computes destination path,
   - moves file using Django storage semantics,
   - updates corresponding `Media` location field(s),
   - persists inside `transaction.atomic()` with clear exception handling and idempotency guards.

4. **Wire approve endpoint to service and preserve auth/permissions**  
   Keep CBV/function-view authorization flow intact (allauth/session auth assumptions unchanged). Ensure only authorized users can trigger the move; return user-safe error messaging.

5. **History and admin visibility**  
   Ensure `django-simple-history` tracks the `Media` location change and approval actor. In admin, confirm updated location is visible/searchable for operational control.

6. **URLs & CBVs/APIs review**  
   No new route expected; if API endpoint exists, ensure serializers/response payload expose updated location where appropriate. Keep backward-compatible response contract.

7. **Templates, semantics, and UX messaging**  
   If review page messaging changes, update template extending `base_generic.html` using semantic HTML5 landmarks, W3.CSS classes, Font Awesome icons, mobile-first behavior, and gettext-wrapped strings.

8. **Filters/pagination integration checks**  
   If media listings use `django-filter`, verify moved-file records remain discoverable by path/status and pagination still behaves correctly after state transition.

9. **Migrations/data handling**  
   Add migration only if schema changes (e.g., missing canonical path/status field). Include reversible migration strategy and MySQL-safe defaults/indexing. Add optional one-off management command for backfill/reconciliation if legacy drift exists.

10. **Testing & CI hardening (Django 5.2/MySQL aware)**  
    Add/adjust pytest suites (unit + integration) to verify:
    - approve action moves file and updates `Media` path in same logical transaction,
    - history entry created,
    - permissions enforced,
    - rollback behavior on move/save failure,
    - CRUM/current-user context correctly set for model-save hooks,
    - monkeypatch targets reference import location used by SUT,
    - patch-target location correctness (avoid patching definition site when call site imports alias),
    - assertions avoid backend-brittle SQL/ordering specifics.
    CI expectations: run main pytest command once (no redundant single-file reruns), enforce repository-configured coverage gate from CI env (do not hard-code stale thresholds), run migration checks, and run docs checks (skip MkDocs-based checks by policy).

11. **Docs/changelog and PR messaging hygiene**  
    Update `/docs/user`, `/docs/admin`, `/docs/development`, and `CHANGELOG.md` with externally readable prose (no internal file/line citations). Ensure PR title/body evolve with later commits so summary always matches latest scope and tests.

12. **Rollout/feature flags and ops safety**  
    Prefer guarded rollout: optional feature toggle around new sync path or staged enablement by environment. Validate in staging with representative media; define rollback by toggling off new path and/or reverting commit/migration with data reconciliation plan.

### Documentation hygiene
- User-facing docs should use descriptive language and stable links, not internal code-path citations.
- Keep docs concise: behavior change, operator steps, troubleshooting, and rollback notes.

### PR messaging guidance
- Initial PR title/body can be broad, but must be revised as commits refine scope.
- Final PR should reflect exact implemented behavior, risk controls, and test evidence.

### Testing/CI expectations
- Use `pytest`/`pytest-django` as primary test entrypoint.
- Honor CI-configured coverage threshold from environment/workflow settings; do not embed outdated percentages in docs or tests.
- Include migration consistency checks for Django 5.2/MySQL compatibility.
- Include docs checks that are repo-approved; skip MkDocs-based checks and explain skip.
- Do not duplicate execution of an individual test module if already covered by main pytest invocation.

## 3️⃣ Tasks (JSON)

```json
[
  {
    "id": "TASK-001",
    "title": "Trace approve-page execution path and identify media-path drift points",
    "description": "Document current control flow from /specimen-lists/pages/<id>/review/ approve action to file move and Media persistence points.",
    "type": "analysis",
    "paths": ["apps/", "templates/"],
    "dependencies": [],
    "acceptance_criteria": [
      "Current move mechanism and DB update sequence are clearly mapped.",
      "Failure points causing file/DB mismatch are identified."
    ],
    "testing": [
      "n/a (analysis task)"
    ]
  },
  {
    "id": "TASK-002",
    "title": "Implement reusable move-and-sync domain service",
    "description": "Create/refactor a single service that moves scan files and updates Media location atomically and idempotently.",
    "type": "backend",
    "paths": ["apps/<review_app>/services.py", "apps/<media_app>/models.py"],
    "dependencies": ["TASK-001"],
    "acceptance_criteria": [
      "Approve flow uses centralized service instead of duplicated logic.",
      "Media object location always matches actual storage path after success.",
      "Exceptions leave system in consistent or recoverable state."
    ],
    "testing": [
      "Unit tests for service success/failure/idempotency",
      "Storage backend interactions mocked at import path used by SUT"
    ]
  },
  {
    "id": "TASK-003",
    "title": "Integrate service into review approve endpoint with permission safeguards",
    "description": "Update existing CBV/function approve handler to call service and preserve authorization checks and user feedback.",
    "type": "backend",
    "paths": ["apps/<review_app>/views.py", "apps/<review_app>/urls.py"],
    "dependencies": ["TASK-002"],
    "acceptance_criteria": [
      "Only authorized users can approve and trigger move.",
      "Endpoint response reflects updated media location state.",
      "No URL contract regressions."
    ],
    "testing": [
      "Integration test for approve endpoint path update",
      "Permission/forbidden tests",
      "Regression test for rollback on move failure"
    ]
  },
  {
    "id": "TASK-004",
    "title": "Ensure auditability via django-simple-history and admin visibility",
    "description": "Verify Media location changes are historized and visible for operators in Django admin.",
    "type": "backend",
    "paths": ["apps/<media_app>/admin.py", "apps/<media_app>/models.py"],
    "dependencies": ["TASK-002"],
    "acceptance_criteria": [
      "History records include location change and actor context where available.",
      "Admin displays current location and supports operator inspection."
    ],
    "testing": [
      "Model/history tests with CRUM current-user setup",
      "Admin smoke test (if project has admin tests)"
    ]
  },
  {
    "id": "TASK-005",
    "title": "Template and i18n/accessibility updates for approval feedback",
    "description": "Adjust review template messaging if needed using semantic HTML5, W3.CSS, Font Awesome, mobile-first layout, and gettext wrappers.",
    "type": "frontend",
    "paths": ["templates/", "apps/<review_app>/templates/"],
    "dependencies": ["TASK-003"],
    "acceptance_criteria": [
      "UI messages clearly indicate successful sync or recoverable errors.",
      "Semantic landmarks and gettext wrapping are present.",
      "No accessibility regression against WCAG AA intent."
    ],
    "testing": [
      "Template rendering tests",
      "Manual keyboard/navigation and responsive check"
    ]
  },
  {
    "id": "TASK-006",
    "title": "Add migration/backfill only if schema gap exists",
    "description": "Create reversible MySQL-safe migration for canonical media location field/index and optional reconciliation command for legacy drift.",
    "type": "migration",
    "paths": ["apps/<media_app>/migrations/", "apps/<media_app>/management/commands/"],
    "dependencies": ["TASK-001"],
    "acceptance_criteria": [
      "Migration is reversible and safe for production data volume.",
      "Backfill/reconciliation plan documented for existing mismatches."
    ],
    "testing": [
      "Migration tests/checks",
      "Dry-run reconciliation command test"
    ]
  },
  {
    "id": "TASK-007",
    "title": "Strengthen pytest coverage and CI checks",
    "description": "Add/adjust tests for atomic sync behavior and ensure CI covers pytest, coverage gate, migrations checks, and docs checks without redundant test runs.",
    "type": "quality",
    "paths": ["apps/", "tests/", ".github/workflows/", "docs/"],
    "dependencies": ["TASK-002", "TASK-003", "TASK-004"],
    "acceptance_criteria": [
      "Main pytest command includes new tests and passes.",
      "Coverage gate from CI environment is met.",
      "Migration checks pass under Django 5.2/MySQL constraints.",
      "No duplicate isolated test execution already covered by main pytest command."
    ],
    "testing": [
      "pytest",
      "makemigrations --check",
      "CI docs check (excluding MkDocs tasks)"
    ]
  },
  {
    "id": "TASK-008",
    "title": "Update docs and changelog with rollout and rollback guidance",
    "description": "Document behavior change and operational procedures in /docs/user, /docs/admin, /docs/development, and CHANGELOG.md.",
    "type": "documentation",
    "paths": ["docs/user/", "docs/admin/", "docs/development/", "CHANGELOG.md"],
    "dependencies": ["TASK-003", "TASK-004", "TASK-007"],
    "acceptance_criteria": [
      "Docs explain new media-location sync behavior and operator expectations.",
      "Rollback instructions and known limitations are present.",
      "No internal code citations in user-facing docs."
    ],
    "testing": [
      "Docs lint/check pipeline used by repository",
      "Manual review for readability and link validity"
    ]
  }
]
```

## 4️⃣ Risks & Mitigations

- **Auth/authorization drift**: Approve action might bypass existing permission decorators when refactored.  
  **Mitigation**: Preserve current permission gate in view layer; add explicit permission tests for positive/negative cases.

- **Data loss / orphan files**: Move succeeds but DB update fails (or vice versa).  
  **Mitigation**: Centralize operation, wrap DB write in transaction, add compensating action or retry-safe idempotent reconciliation command.

- **Historical/audit gaps**: Media path updates not captured in history.  
  **Mitigation**: Validate `django-simple-history` tracking on location field and user attribution via CRUM in tests.

- **MySQL-specific behavior**: Collation/case sensitivity or transaction semantics may differ from local SQLite assumptions.  
  **Mitigation**: Avoid backend-specific assertions; run CI against MySQL-configured environment and keep migration SQL portable.

- **Performance regression on large files/storage**: synchronous move could slow approval UX.  
  **Mitigation**: Measure move latency; if needed, add staged async follow-up with explicit pending status (deferred scope).

- **Accessibility regressions**: status/error message updates may not be announced clearly.  
  **Mitigation**: Use semantic landmarks, proper heading hierarchy, visible focus states, and accessible status messaging.

- **Localization gaps**: new UI strings not translatable.  
  **Mitigation**: Wrap user-visible strings with gettext and include in localization workflow.

- **Dependency/security risk**: introducing new package for file operations adds supply-chain risk.  
  **Mitigation**: use standard Django/Python storage APIs already in stack; avoid new dependency.

- **Rollback complexity**: partial rollout could leave mixed path states.  
  **Mitigation**: provide rollback runbook with feature toggle disable + reconciliation command to realign DB paths.

## 5️⃣ Out-of-Scope

- Re-architecting the entire media pipeline or introducing new storage providers.
- Building a generic asynchronous job framework solely for this feature.
- Bulk historical remediation beyond a targeted reconciliation command/runbook.
- Redesigning unrelated specimen review UI flows beyond required approval feedback changes.
- New external integrations (e.g., antivirus/DLP scanning) not currently in scope.

## 6️⃣ Definition of Done ✅

- [ ] Acceptance criteria for approve-page media sync are satisfied end-to-end.
- [ ] Unit and integration tests are green under `pytest`/`pytest-django` and CI coverage gate is met.
- [ ] Migrations created/applied (if needed) and migration checks pass.
- [ ] Django admin integration updated for media location observability.
- [ ] `django-simple-history` captures media location changes with actor context where available.
- [ ] `django-filter`-based listing behavior remains correct for moved media records.
- [ ] Templates remain mobile-first, extend `base_generic.html`, and use semantic HTML5 landmarks.
- [ ] User-visible strings are wrapped for i18n/localization.
- [ ] Any requirements changes are justified and prompt snapshot refresh is run if requirements changed.
- [ ] Docs updated in `/docs/user`, `/docs/admin`, `/docs/development`, and `CHANGELOG.md`.
- [ ] CI is green (tests, coverage gate, migrations check, docs checks).
- [ ] Staging validation completed with representative specimen pages/media moves.
- [ ] Feature behavior demoed to stakeholders.
- [ ] Rollback plan tested/confirmed (toggle/revert + reconciliation steps).
