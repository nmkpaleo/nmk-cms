# Specimen List Side/Portion Inference Plan

## 1️⃣ Assumptions & Scope
- Django 5.2.11 + MySQL are the runtime constraints; inference logic should run inside the existing synchronous `approve_page` workflow to preserve transaction boundaries and avoid eventual-consistency edge cases.
- The target behavior applies to the specimen list page review endpoint (`specimen-lists/pages/<id>/review/`) when reviewers click **Approve page**.
- Inference is a fallback only: if `NatureOfSpecimen.side` or `NatureOfSpecimen.portion` is already present in row payload, do not overwrite reviewer-provided values.
- Side inference should normalize abbreviations and variants (e.g., `Lt`, `L`, `Left`; `Rt`, `R`, `Right`) to canonical lowercase `left`/`right` values used in current persistence and tests.
- Portion inference should normalize abbreviations and variants (e.g., `Dist`, `Distal`; `Prox`, `Proximal`) to canonical lowercase `distal`/`proximal` values.
- No new Django app is required; this is a targeted enhancement in existing specimen list approval and parsing services.

**Apps to modify or create**
- **Modify:** `app/cms` (review approval service, optional OCR/row normalization helper, tests), `docs` (development plan + user/admin behavior notes), and `CHANGELOG.md`.
- **Create:** no new app.

**Reused vs. new models/forms/views**
- **Reuse:** existing `SpecimenListPageReviewView`, approval flow in `cms.services.review_approval`, and existing `NatureOfSpecimen` persistence model.
- **New:** a small reusable inference helper (service/util function) for parsing element-content tokens and returning normalized `side`/`portion` fallback values; no model/schema changes expected.

**Required packages**
- **No new dependencies**. Existing stack already supports this feature; pattern matching can be implemented with Python stdlib (`re`) and existing Django services.

## 2️⃣ High-Level Plan (5–12 steps)
1. **Confirm canonical vocab and constraints**: Validate accepted `NatureOfSpecimen.side` and `NatureOfSpecimen.portion` values used by forms/admin exports to avoid introducing value drift (`left/right`, `distal/proximal`).
2. **Add inference helper**: Implement a DRY utility in `cms.services` (or existing review utility module) that inspects element content text and extracts side/portion using case-insensitive token matching with word boundaries and punctuation tolerance.
3. **Integrate into approval mapping**: Update page approval row-to-model mapping so missing `side`/`portion` fields are backfilled from inferred values derived from element contents before `NatureOfSpecimen` creation/update.
4. **Preserve explicit reviewer data**: Add guardrails to ensure inference only applies when target fields are blank/null; never override manually curated row values during approval.
5. **Audit trail alignment**: Ensure django-simple-history entries still capture final stored values for `NatureOfSpecimen`; no extra model changes needed, but verify history visibility in admin/review audits.
6. **Review UI/CBV contract check**: Keep existing URLs and class-based views unchanged; if helpful for reviewer trust, optionally surface inferred values in post-approval feedback messages without altering current permissions model.
7. **Filtering & pagination compatibility**: Confirm existing django-filter queue/review lists remain unaffected because persistence schema is unchanged; update filter tests where inferred values influence downstream list display.
8. **Admin integration verification**: Confirm admin list/search/export for `NatureOfSpecimen` display normalized inferred values correctly and do not break import/export workflows.
9. **Testing and CI hardening**: Add pytest/pytest-django unit tests for inference helper and integration tests for approve-page flow, including ambiguity/negative cases and MySQL-safe transactional behavior.
10. **Docs/changelog updates**: Update docs for reviewer/admin expectations (fallback inference behavior, canonical values, non-overwrite rule) and `CHANGELOG.md`; keep user-facing docs citation-free and descriptive.
11. **Rollout + feature flag strategy**: Gate inference behind a settings flag (default-on in staging, configurable in production) to allow low-risk rollback by config without database rollback.

**Documentation hygiene**
- User/admin docs should describe behavior in clear prose and external-facing links only; avoid internal file/line citations.

**PR messaging**
- Start PR with a focused title on side/portion inference, then update title/body if scope expands (e.g., adding feature flag or UI hints) so the final description matches the merged behavior.

**Testing/CI expectations (Django 5.2/MySQL)**
- Run pytest/pytest-django suites and maintain coverage ≥ 90% for touched modules.
- Run migrations checks (`makemigrations --check`, `migrate --check`) even if no schema changes are expected.
- Run lint/type checks configured in repo.
- Run docs lint/build steps used by CI; skip MkDocs-specific steps per project policy.

### T4 implementation runbook (CI, rollout, rollback)

**CI gate checklist (required before merge)**
- `pytest --maxfail=1`
- `pytest --cov=app/cms --cov-report=term-missing` (target: **>= 90%** coverage for touched modules)
- `python app/manage.py makemigrations --check`
- `python app/manage.py migrate --check`
- Run project docs checks used in CI; if any step invokes MkDocs, skip that step and record the skip reason in the PR because docs are plain Markdown in this repository.

**Runtime toggle and defaults**
- Setting: `SPECIMEN_LIST_ENABLE_SIDE_PORTION_INFERENCE`
- Recommended defaults:
  - staging: `True`
  - production initial rollout: `True`
  - emergency rollback: set to `False` and redeploy/reload config

**Rollback procedure (no schema rollback required)**
1. Set `SPECIMEN_LIST_ENABLE_SIDE_PORTION_INFERENCE=False` in runtime environment.
2. Reload app processes (Gunicorn/container restart) to pick up the setting.
3. Re-approve a known sample row and confirm Side/Portion are no longer auto-filled when blank.
4. Keep existing records unchanged; perform targeted audit query on recent approvals if needed.

**Staging verification script (representative token coverage)**
Run these examples in staging to confirm expected behavior:
- `Lt femur Dist` -> `side=left`, `portion=distal`
- `Rt humerus Prox` -> `side=right`, `portion=proximal`
- `Left tibia` -> `side=left`, `portion=None`
- `Prox radius` -> `side=None`, `portion=proximal`
- `Lt Rt ulna` -> `side=None` (ambiguous), `portion=None`

Record outputs in release notes/PR comments before production promotion.

## 3️⃣ Tasks (JSON)
[
  {
    "id": "T1",
    "title": "Define canonical side/portion inference rules",
    "summary": "Document and codify accepted token variants and canonical outputs for Side and Portion fallback inference.",
    "app": "apps.cms",
    "files_touched": [
      "app/cms/services/review_approval.py",
      "docs/development/specimen_list_side_portion_inference_plan.md"
    ],
    "migrations": false,
    "settings_changes": [],
    "packages": [],
    "permissions": [
      "cms.review_specimenlistpage"
    ],
    "acceptance_criteria": [
      "Token map includes Lt/Rt/Left/Right and Dist/Prox/Distal/Proximal variants.",
      "Canonical outputs are stable and aligned with NatureOfSpecimen usage across admin/forms."
    ],
    "test_plan": [
      "pytest: unit tests for token normalization and ambiguous/no-match handling."
    ],
    "docs_touched": [
      "docs/development/specimen_list_side_portion_inference_plan.md"
    ],
    "dependencies": [],
    "estimate_hours": 2.5,
    "risk_level": "low",
    "priority": "high",
    "reviewer_notes": [
      "Confirm casing and vocabulary expected by exports and downstream consumers."
    ]
  },
  {
    "id": "T2",
    "title": "Implement fallback inference helper in approval pipeline",
    "summary": "Add DRY helper logic to infer missing NatureOfSpecimen side/portion from element content text during page approval.",
    "app": "apps.cms",
    "files_touched": [
      "app/cms/services/review_approval.py",
      "app/cms/views.py"
    ],
    "migrations": false,
    "settings_changes": [
      "Optional feature flag: SPECIMEN_LIST_ENABLE_SIDE_PORTION_INFERENCE"
    ],
    "packages": [],
    "permissions": [
      "cms.review_specimenlistpage",
      "cms.approve_specimenlistpage"
    ],
    "acceptance_criteria": [
      "Approve page populates side/portion when row values are blank and inferable from element content.",
      "Existing explicit side/portion values are never overwritten by inferred values.",
      "No changes to URL routing or review lock behavior."
    ],
    "test_plan": [
      "pytest: integration tests covering approve-page workflow with missing vs explicit values.",
      "pytest: regression tests for lock/permission paths to ensure unchanged behavior."
    ],
    "docs_touched": [
      "docs/user/specimen-list-review.md",
      "docs/admin/specimen-list-review.md"
    ],
    "dependencies": [
      "T1"
    ],
    "estimate_hours": 6.0,
    "risk_level": "medium",
    "priority": "high",
    "reviewer_notes": [
      "Prefer small pure function(s) for parsing to keep matching logic testable and reusable."
    ]
  },
  {
    "id": "T3",
    "title": "Validate admin/history/filter compatibility",
    "summary": "Ensure inferred values propagate cleanly through admin displays, history entries, and existing filters without schema changes.",
    "app": "apps.cms",
    "files_touched": [
      "app/cms/admin.py",
      "app/cms/tests/test_specimen_list_review_approval.py",
      "app/cms/tests/test_review_workflow.py"
    ],
    "migrations": false,
    "settings_changes": [],
    "packages": [],
    "permissions": [
      "cms.view_natureofspecimen",
      "cms.review_specimenlistpage"
    ],
    "acceptance_criteria": [
      "Admin pages render inferred canonical values without validation errors.",
      "django-simple-history records final persisted side/portion values.",
      "Existing queue/review filters continue working with inferred data."
    ],
    "test_plan": [
      "pytest: admin/history assertions for inferred values.",
      "pytest: filter/list assertions where inferred values are present."
    ],
    "docs_touched": [
      "docs/admin/specimen-list-review.md",
      "CHANGELOG.md"
    ],
    "dependencies": [
      "T2"
    ],
    "estimate_hours": 3.5,
    "risk_level": "low",
    "priority": "medium",
    "reviewer_notes": [
      "Avoid broad admin refactors; keep scope limited to compatibility checks and minimal presentation updates."
    ]
  },
  {
    "id": "T4",
    "title": "CI, rollout, and rollback readiness",
    "summary": "Harden release plan with tests, coverage, migration checks, and config-based rollback guidance.",
    "app": "project",
    "files_touched": [
      "docs/development/specimen_list_side_portion_inference_plan.md",
      "docs/development/automation.md",
      "CHANGELOG.md"
    ],
    "migrations": false,
    "settings_changes": [
      "Document runtime toggle and default environment values"
    ],
    "packages": [],
    "permissions": [],
    "acceptance_criteria": [
      "CI checklist explicitly includes pytest/pytest-django, coverage >= 90%, and migration checks.",
      "Rollback plan can disable inference immediately via configuration.",
      "Staging verification script covers representative Lt/Rt/Dist/Prox samples."
    ],
    "test_plan": [
      "pytest --maxfail=1",
      "pytest --cov=app/cms --cov-report=term-missing",
      "python app/manage.py makemigrations --check",
      "python app/manage.py migrate --check"
    ],
    "docs_touched": [
      "docs/development/specimen_list_side_portion_inference_plan.md",
      "docs/development/automation.md",
      "CHANGELOG.md"
    ],
    "dependencies": [
      "T2",
      "T3"
    ],
    "estimate_hours": 2.0,
    "risk_level": "low",
    "priority": "medium",
    "reviewer_notes": [
      "If docs tooling references MkDocs, skip that step and record reason in PR per repo guidance."
    ]
  }
]

## 4️⃣ Risks & Mitigations
- **Auth/permission regression risk**: Approval logic changes may accidentally bypass role checks.
  - *Mitigation*: Keep inference in service layer after permission gates; add regression tests for unauthorized approval attempts.
- **Data quality risk (false positives)**: Tokens like `R` or `L` can appear in unrelated contexts.
  - *Mitigation*: Use strict boundary-aware patterns, prioritize unambiguous forms (`Lt`, `Rt`, `Dist`, `Prox`), and leave fields empty when confidence is low.
- **Data loss/overwrite risk**: Inference could overwrite manually entered values.
  - *Mitigation*: Apply inference only when target fields are blank; assert non-overwrite behavior in integration tests.
- **Performance risk**: Additional parsing in page approval could increase latency.
  - *Mitigation*: Keep parsing O(n) simple regex on short element strings; avoid extra DB round-trips.
- **Accessibility risk**: If UI messaging is added, it may not be screen-reader friendly.
  - *Mitigation*: Use semantic alerts/status regions and existing W3.CSS accessible patterns; keyboard-only verification in QA.
- **Localization risk**: New user-facing labels/messages may bypass translation.
  - *Mitigation*: Wrap all new strings in gettext and run message extraction checks.
- **Dependency/security risk**: Introducing new parser libs could increase CVE surface.
  - *Mitigation*: avoid new dependencies; rely on stdlib and existing vetted packages.
- **Rollback risk**: Logic issue in production could impact newly approved pages.
  - *Mitigation*: ship behind feature flag and document immediate config rollback + targeted data audit query for recently approved pages.

## 5️⃣ Out-of-Scope
- Backfilling historical `NatureOfSpecimen` records created before this feature.
- Expanding inference to additional fields beyond Side and Portion.
- Introducing OCR model/prompt changes for richer natural-language extraction.
- Building new review UI pages or redesigning queue UX beyond minimal messaging.
- Non-English anatomical synonym detection beyond current requested token set.

## 6️⃣ Definition of Done ✅
- [ ] Acceptance criteria for side/portion fallback inference on **Approve page** are satisfied.
- [ ] Unit + integration tests pass with coverage ≥ 90% for touched modules.
- [ ] Migration checks pass; no unexpected schema changes (or migrations applied if needed).
- [ ] Admin integration is verified for inferred values.
- [ ] django-simple-history reflects final persisted side/portion values.
- [ ] django-filter flows remain valid for queue/review pages.
- [ ] Mobile-first templates remain intact where reviewer messaging is updated.
- [ ] Semantic HTML5 landmarks remain valid in touched templates.
- [ ] All user-facing strings are wrapped for i18n/gettext.
- [ ] Requirements changes are justified (none expected).
- [ ] Docs updated in `/docs/user`, `/docs/admin`, `/docs/development`, and `CHANGELOG.md`.
- [ ] CI is green (pytest/pytest-django, coverage, migrations, lint/type checks, docs checks excluding MkDocs).
- [ ] Staging verification completed with representative Lt/Rt/Dist/Prox examples.
- [ ] Feature demo completed with reviewer workflow walk-through.
- [ ] Rollback plan validated (feature flag off path confirmed).
