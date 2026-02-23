# Field Slip OCR Prompt + QC Ingestion Plan

## 1️⃣ Assumptions & Scope

### Django-specific assumptions
- The existing OCR entrypoint remains `app/cms/ocr_processing.py` (`detect_card_type` → `build_prompt_for_card_type` → `chatgpt_ocr`) and already distinguishes `accession_card` vs `field_slip`.
- `FieldSlip` and related lookup models already exist (`SedimentaryFeature`, `FossilGroup`, `PreservationState`, `CollectionMethod`, `GrainSize`) and should be reused instead of introducing parallel enums/tables.
- `FieldSlip` is already historical via `django-simple-history`, so QC/approval writes should continue to create history entries without bespoke audit storage.
- Existing QC workflow for accession cards (intern/expert wizard, `MediaQCLog`, status transitions) is the canonical pattern; field-slip review should plug into the same state machine.
- MySQL + Django 5.2 constraints: avoid fragile schema churn; prefer additive migrations and deterministic data migrations for new normalized mappings.

### Apps to modify or create
- **Modify**: `app/cms` only (models already centralized there).
- **No new app**: feature fits existing OCR/QC domain and avoids routing/auth duplication.
- **Likely touched areas**:
  - OCR extraction: `app/cms/ocr_processing.py`
  - QC forms/wizard assembly/persistence: `app/cms/views.py`
  - QC approval path: `app/cms/services/review_approval.py`
  - Admin + filters if field-slip QC visibility expands: `app/cms/admin.py`, `app/cms/forms.py`/`filters.py`
  - Templates for intern/expert field-slip sections: `app/cms/templates/cms/qc/*.html`
  - Docs/changelog: `docs/user`, `docs/admin`, `docs/development`, `CHANGELOG.md`

### Reused vs. new models/forms/views
- **Reuse**
  - `FieldSlip`, `AccessionFieldSlip`, `MediaQCLog`, `MediaQCComment`
  - Existing intern/expert QC wizard views and queue views
  - Existing accession-card prompt contract style (`raw/interpreted/confidence` objects)
- **Net-new (planned)**
  - A structured **field-slip JSON contract** (API prompt schema) aligned with current OCR payload semantics.
  - Field-slip-specific normalization helpers (checkbox parsing, provenance mapping, accession row suffix expansion).
  - Expanded `FieldSlipQCForm`/formset fields for sedimentary & provenance metadata.
  - Optional lightweight service module for mapping free-text checkbox tokens to lookup models (to keep DRY between OCR import and QC approval).

### Required packages
- No new third-party dependency expected.
- Existing dependencies cover scope:
  - `openai` for prompt execution.
  - `django-simple-history` for audit trail.
  - `django-filter` for any QC/admin filter additions.
  - `django-formtools` and Django forms for wizard steps.

---

## 2️⃣ High-Level Plan (5–12 steps)

1. **Define canonical field-slip OCR JSON contract and confidence semantics**
   - Introduce a strict JSON shape for `card_type="field_slip"` matching existing accession-card conventions (`raw`, `interpreted`, optional confidence).
   - Include explicit arrays/objects for checkbox groups and provenance decomposition to avoid ad-hoc parsing.
   - Include source variants (`DISCOVERER`/`FINDER`, `ACCESSION. KNM`/`ACC.# KNM`, handwritten KNM in corner) in prompt rules.

2. **Design provenance/checkbox mapping matrix (normalization spec first)**
   - Map scan options to model targets:
     - `BED/UNIT DERIVED FROM` → `sedimentary_features` M2M
     - Rock Type options split into `fossil_groups` + `preservation_states`
     - `RECOMMEND` → `recommended_methods`
     - `PROVENANCE` → `collection_position`, `surface_exposure`, `matrix_association`
     - `MATRIX` → `matrix_grain_size`
   - Document deterministic precedence when multiple boxes are checked (e.g., `SURFACE WITH MATRIX` overrides ambiguous combinations).

3. **Upgrade field-slip OCR prompt implementation in `build_prompt_for_card_type`**
   - Replace current generic field-slip prompt with implementation-ready, schema-locked instructions.
   - Add anti-hallucination and null-handling rules (`do not invent`, keep uncertain in `raw`, set `interpreted` null when unresolved).
   - Require extraction from both front/back and comments on reverse side.

4. **Add field-slip payload normalization + validation layer (service/helper)**
   - Parse OCR payload into internal normalized structure before QC rendering.
   - Handle accession suffix ranges (`A-C`) and row letters, producing deterministic accession-link candidates.
   - Add guarded parsing for integer-only `fragments` and free-text date retention for `verbatimEventDate` while optionally deriving `collection_date` when parseable.

5. **Extend QC wizard for field-slip parity with accession-card path**
   - Expand `FieldSlipQCForm` with new fields/checkbox controls for all listed model targets.
   - Ensure intern/expert templates render semantic HTML5 sections (`section`, `fieldset`, `legend`) and existing W3.CSS classes; keep mobile-first layout.
   - Preserve per-field diff logging into `MediaQCLog` (`OCR_DATA`) for both simple and M2M changes.

6. **Implement approval pipeline for reviewed field slips**
   - On expert approval, create/update `FieldSlip` and `AccessionFieldSlip` atomically.
   - Resolve lookup relations via normalized dictionary tables (case-insensitive matching + safe fallback behavior).
   - Keep idempotency: repeated approvals of same reviewed payload should not duplicate M2M links or accession links.

7. **Permissions/auth and URLs/CBV alignment**
   - Reuse existing QC access controls (intern vs expert groups, staff restrictions).
   - No new public endpoint; extend existing wizard POST handling.
   - Verify unauthorized users cannot mutate QC payloads or approve field-slip creation.

8. **Admin/filter enhancements and history visibility**
   - Confirm admin pages expose newly populated field-slip metadata and history deltas.
   - If needed, extend `django-filter` configs so staff can query by new normalized relations (sedimentary features/matrix/provenance states).
   - Ensure pagination/performance is preserved with prefetch/select_related for QC and list views.

9. **Testing & CI gates (Django 5.2/MySQL-aware)**
   - Add pytest/pytest-django unit tests for prompt contract parser, checkbox mappings, provenance resolver, accession suffix handling.
   - Add integration tests for intern save, expert approve, and rollback-friendly failure paths (transaction atomicity).
   - Run quality gates: coverage ≥ 90%, `makemigrations --check --dry-run`, Django checks, docs lint/build that **skips MkDocs** per repo policy.

10. **Docs, changelog, rollout and feature-flag strategy**
   - Update user/admin/development docs with reviewer workflow and extraction behaviors (descriptive prose, no internal code citations in user-facing docs).
   - Add CHANGELOG entry with scope + operational notes.
   - Gate rollout behind existing OCR/QC feature toggles or new field-slip extraction flag for safe staged release.
   - PR messaging rule: keep title/body synced with latest commit scope; amend summary when scope evolves.

---

## 3️⃣ Tasks (JSON)

```json
{
  "epic": "field-slip-ocr-qc-parity",
  "tasks": [
    {
      "id": "FS-001",
      "title": "Define field-slip OCR JSON schema and mapping spec",
      "type": "design",
      "paths": [
        "docs/development/field_slip_ocr_qc_plan.md",
        "docs/development/*.md"
      ],
      "depends_on": [],
      "acceptance_criteria": [
        "Schema covers all requested field-slip fields including checkbox groups, provenance decomposition, accession linkage variants, and comments/back-side text.",
        "Mapping rules define deterministic precedence for conflicting/overlapping checkbox states.",
        "Spec clarifies null handling, confidence semantics, and anti-hallucination constraints."
      ]
    },
    {
      "id": "FS-002",
      "title": "Implement strict field-slip prompt in OCR card-type builder",
      "type": "backend",
      "paths": [
        "app/cms/ocr_processing.py",
        "app/cms/tests.py"
      ],
      "depends_on": [
        "FS-001"
      ],
      "acceptance_criteria": [
        "`build_prompt_for_card_type('field_slip')` returns schema-locked prompt instructions.",
        "Prompt output contract enforces JSON-only responses with raw/interpreted/confidence objects.",
        "Tests validate key schema instructions and regression against fallback generic prompt."
      ]
    },
    {
      "id": "FS-003",
      "title": "Add field-slip payload normalization/parsing helpers",
      "type": "backend",
      "paths": [
        "app/cms/ocr_processing.py",
        "app/cms/services/review_approval.py",
        "app/cms/tests.py"
      ],
      "depends_on": [
        "FS-002"
      ],
      "acceptance_criteria": [
        "Checkbox and provenance values normalize into model-ready fields consistently.",
        "Accession identifiers with row suffix ranges are expanded and validated deterministically.",
        "Fragments parsing stores integers only and safely ignores non-numeric noise."
      ]
    },
    {
      "id": "FS-004",
      "title": "Expand QC forms and wizard rendering for full field-slip review",
      "type": "backend",
      "paths": [
        "app/cms/views.py",
        "app/cms/templates/cms/qc/wizard_base.html",
        "app/cms/templates/cms/qc/intern_wizard.html",
        "app/cms/templates/cms/qc/expert_wizard.html",
        "app/cms/tests.py"
      ],
      "depends_on": [
        "FS-003"
      ],
      "acceptance_criteria": [
        "Intern and expert QC UIs expose all new field-slip fields with semantic HTML5 landmarks/fieldsets and mobile-first layout.",
        "QC saves keep per-field differences for audit logs and preserve existing accession-card behavior.",
        "Localization wrappers are applied to newly introduced labels/messages."
      ]
    },
    {
      "id": "FS-005",
      "title": "Create approval ingestion path for reviewed field slips with relations",
      "type": "backend",
      "paths": [
        "app/cms/services/review_approval.py",
        "app/cms/ocr_processing.py",
        "app/cms/models.py",
        "app/cms/tests.py"
      ],
      "depends_on": [
        "FS-004"
      ],
      "acceptance_criteria": [
        "Expert approval creates/updates FieldSlip plus AccessionFieldSlip links inside atomic transactions.",
        "M2M/FK relations resolve via existing lookup tables without duplicate relation rows.",
        "Repeated approvals are idempotent and preserve django-simple-history entries."
      ]
    },
    {
      "id": "FS-006",
      "title": "Admin/filter and permissions hardening for new field-slip metadata",
      "type": "backend",
      "paths": [
        "app/cms/admin.py",
        "app/cms/forms.py",
        "app/cms/filters.py",
        "app/cms/views.py",
        "app/cms/tests.py"
      ],
      "depends_on": [
        "FS-005"
      ],
      "acceptance_criteria": [
        "Staff can inspect and filter new field-slip metadata efficiently (with prefetch/select_related where needed).",
        "QC/approval endpoints continue enforcing group-based permissions.",
        "No regression in existing queue pagination/filter behavior."
      ]
    },
    {
      "id": "FS-007",
      "title": "Testing, docs, changelog, and rollout controls",
      "type": "test",
      "paths": [
        "app/cms/tests.py",
        "tests/",
        "docs/user/quality-control.md",
        "docs/admin/fieldslips.md",
        "docs/development/*.md",
        "CHANGELOG.md",
        ".github/workflows/*.yml"
      ],
      "depends_on": [
        "FS-006"
      ],
      "acceptance_criteria": [
        "pytest/pytest-django suite covers new extraction, QC, and approval flows with total coverage >= 90%.",
        "CI includes migration drift checks and docs verification while explicitly avoiding MkDocs build steps.",
        "Changelog and user/admin/development docs reflect final behavior and rollout/rollback guidance."
      ]
    }
  ]
}
```

---

## 4️⃣ Risks & Mitigations

- **Auth/authorization drift risk**: Expanded QC forms may expose expert-only actions.
  - **Mitigation**: Reuse existing group-gated wizard endpoints and add negative permission tests (intern cannot approve).

- **Data migration / mapping drift risk**: Existing lookup tables may not contain all checkbox labels exactly as written on cards.
  - **Mitigation**: Add deterministic normalization aliases; log unresolved values into QC comments for manual correction rather than silent drop.

- **Data loss risk during approval**: Overwriting existing FieldSlip values when partial OCR payload arrives.
  - **Mitigation**: Merge strategy that updates only reviewed fields; preserve prior values when reviewed value is blank/null unless reviewer explicitly clears.

- **Performance risk**: Additional relation hydration in QC and list filters could trigger N+1 queries.
  - **Mitigation**: prefetch M2M + select_related FK in QC/form initializers and list views; add query-count assertions in tests where practical.

- **Accessibility risk**: New checkbox-heavy forms can degrade keyboard/screen-reader usability.
  - **Mitigation**: semantic fieldsets/legends, explicit labels/help text, focus order checks, adequate contrast with current W3.CSS tokens.

- **Localization risk**: New labels/messages remain hardcoded English.
  - **Mitigation**: wrap all new strings in gettext utilities and verify extraction in i18n pipeline.

- **Dependency vulnerability risk**: Introducing extra parser libraries could expand attack surface.
  - **Mitigation**: use existing stdlib + project deps; if new package becomes necessary, pin and document rationale/security review.

- **Rollback risk**: Prompt/schema rollout could degrade extraction quality.
  - **Mitigation**: feature flag for field-slip strict schema path; ability to revert to previous prompt quickly without schema rollback.

---

## 5️⃣ Out-of-Scope

- Building a separate standalone field-slip OCR microservice.
- Replacing current OCR provider stack or adding new LLM vendors.
- Historical backfill/reprocessing of all existing field-slip media (can be planned as a follow-up batch job).
- Advanced geospatial normalization (coordinate parsing to decimal degrees with CRS inference) beyond verbatim capture.
- Automatic taxonomic authority reconciliation for `verbatim_taxon`.

---

## 6️⃣ Definition of Done ✅

- [ ] Acceptance criteria for all approved tasks are satisfied.
- [ ] Unit + integration tests pass with coverage ≥ 90%.
- [ ] `makemigrations --check --dry-run` passes; migrations applied in target environments if introduced.
- [ ] Admin integration for new/updated field-slip metadata is complete.
- [ ] `django-simple-history` captures field-slip/QC approval changes.
- [ ] `django-filter` integration covers new filterable field-slip metadata (where applicable).
- [ ] QC templates are mobile-first and use semantic HTML5 landmarks.
- [ ] New user-facing strings are wrapped for i18n.
- [ ] Any requirements changes are justified and dependency snapshot refreshed with `python docs/scripts/update_prompts.py`.
- [ ] Documentation updated in `/docs/user`, `/docs/admin`, `/docs/development`, plus `CHANGELOG.md`.
- [ ] CI pipeline is green (pytest/pytest-django, migration checks, docs verification without MkDocs).
- [ ] Staging workflow verified end-to-end (OCR → intern QC → expert QC → field-slip creation/linking).
- [ ] Feature demoed to stakeholders.
- [ ] Rollback plan documented and confirmed.
