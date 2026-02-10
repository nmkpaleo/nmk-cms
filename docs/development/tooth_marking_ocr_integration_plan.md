# Tooth-Marking OCR Integration Plan (Implementation-Ready)

## 1️⃣ Assumptions & Scope

### Django-specific assumptions
- Project is Django 5.2.9 with MySQL and `django-simple-history` already active on key OCR/QC models.
- Current OCR pipeline is OpenAI Vision–first for both accession cards and specimen list pages; this plan keeps that behavior and inserts tooth-marking correction as an incremental post-processing layer.
- We will not refactor existing ingestion or approval flows; we add bounded hooks in existing services/functions.
- Bounding-box OCR must be CPU-friendly on Linux servers; Tesseract is primary engine, PaddleOCR optional behind a feature flag.
- Backward compatibility is required: if box OCR is disabled/missing dependencies, pipeline must proceed using raw element text.

### Apps to modify or create
- Modify existing `app/cms` app only.
- Add new package: `app/cms/ocr_boxes/`.
- Add integration module: `app/cms/tooth_markings/integration.py`.
- Update OCR pipeline integration points in existing services (`ocr_processing`, specimen-list approval/review path).
- Add tests under `app/cms/tests/`.
- Add developer docs under `docs/development/`.

### Reused vs. new models/forms/views
- **Reuse**: `Media`, `SpecimenListPageOCR`, `SpecimenListRowCandidate`, `NatureOfSpecimen`, existing QC views and approval services.
- **Likely model update (minimal)**: add JSON/text fields where needed to preserve `element_raw`, `element_corrected`, and detection metadata before QC persistence.
- **No new Django app**.
- **No broad UI refactor**; QC pages can initially display metadata via existing context/JSON rendering patterns.

### Required packages
- Reuse existing OCR stack and PIL dependency (`pillow`).
- Add `pytesseract` for token box extraction (justified by simple deploy and TSV boxes).
- Keep PaddleOCR optional and gated (`OCR_BOX_ENGINE=paddle`) to avoid mandatory heavy dependencies.
- Document system package dependency: `tesseract-ocr`.

### Repo archaeology map (current pipeline)

#### Accession card upload/OCR/ChatGPT extraction
- Upload staging and media creation: `cms.upload_processing.process_file`.
- Card classification + GPT OCR + media OCR payload persistence + QC pending status: `cms.ocr_processing._process_single_scan`.
- GPT OCR entry point: `cms.ocr_processing.chatgpt_ocr`.
- Parsed OCR “element / nature” extraction into structured rows: `cms.ocr_processing._extract_entry_components` (builds `rows[*].natures[*].verbatim_element`, `element_name`).
- Persistence to domain models before/at QC approval flows: `cms.ocr_processing._apply_rows` and `cms.ocr_processing.create_accessions_from_media`.

#### Specimen list PDF processing pipeline
- PDF split to images: `cms.upload_processing.process_specimen_list_pdf` + `_split_pdf_page_to_image` (`pdftoppm`).
- Page-type classification queue: `cms.tasks.classify_pending_specimen_pages` -> `cms.ocr_processing.classify_specimen_list_page`.
- Raw OCR queue: `cms.tasks.run_specimen_list_ocr_queue` -> `cms.ocr_processing.run_specimen_list_raw_ocr`.
- Row extraction queue: `cms.tasks.run_specimen_list_row_extraction_queue` -> `cms.ocr_processing.run_specimen_list_row_extraction`.

#### QC step and where element is set before QC
- Specimen-list QC approval write path: `cms.services.review_approval.approve_row`.
- Element assignment before QC persistence: `cms.services.review_approval._build_nature_of_specimen` (uses `row_data["element"]` / `row_data["verbatim_element"]`).
- For accession-card created accessions, element/nature persistence occurs in `cms.ocr_processing._apply_rows` via `NatureOfSpecimen.objects.create(...)`.

---

## 2️⃣ High-Level Plan (5–12 steps)

1. **Introduce OCR box abstraction package (`cms/ocr_boxes`)**
   - Add `TokenBox` dataclass and engine protocol in `base.py`.
   - Add engine resolver and public API in `service.py`: `get_token_boxes(image, roi=None)` and `get_token_crops(image, token_boxes)`.

2. **Implement Tesseract token-box backend first (`tesseract_boxes.py`)**
   - Use `pytesseract.image_to_data(..., output_type=DICT)`.
   - Convert TSV rows into normalized `TokenBox` objects.
   - Support ROI OCR with coordinate remap to full-page space.
   - Preserve stable per-page `token_id`; include optional `line_id`/`block_id` when present.

3. **Add optional PaddleOCR backend (`paddle_boxes.py`) behind flag**
   - Load only when selected by env var and dependency present.
   - On import/runtime failure, log warning and fallback to tesseract/no-op per feature flag policy.

4. **Create tooth-marking integration helper (`cms/tooth_markings/integration.py`)**
   - Implement `apply_tooth_marking_correction(page_image, element_text, roi=None)`.
   - Pipeline: token boxes -> token crops -> `correct_element_text(...)`.
   - Return deterministic payload: raw input, corrected output, detections, replacements applied, confidence-filtered decisions.

5. **Hook accession-card OCR flow pre-QC**
   - Integration point: after OCR JSON parse (or just before `_apply_rows` writes nature rows), where element/verbatim element is available.
   - For each candidate element text, keep `element_raw`; compute/store `element_corrected`.
   - Apply confidence gate (`TOOTH_MARKING_MIN_CONF`, default `0.85`) before rewriting tokens.
   - Fail-safe behavior: if box OCR unavailable/fails, keep raw text and continue pipeline.

6. **Hook specimen-list flow pre-QC persistence**
   - Integration point: when row candidates are built or normalized before `approve_row` writes domain objects.
   - Phase 1: token-driven matching over full page boxes (no per-row ROI yet).
   - Persist corrected element in row candidate data used by QC (`element` and/or `verbatim_element`), while preserving raw value.

7. **Minimal schema update for QC evidence (JSON-first)**
   - Add JSON/text fields on extracted record(s) used by QC (recommended: row candidate data schema first; optional dedicated JSONField for accession-card extraction metadata).
   - Store detection evidence: token, notation, confidence, bbox, whether replacement applied.
   - Add migrations compatible with MySQL JSON support.

8. **Logging, observability, and feature flags**
   - Add structured logs with page/media IDs: number of suspect tokens, detections, applied replacements, fallback reasons.
   - Feature flags/env vars:
     - `TOOTH_MARKING_ENABLED` (default true in non-test env)
     - `OCR_BOX_ENABLED` (default true when engine available)
     - `OCR_BOX_ENGINE=tesseract|paddle`
     - `TOOTH_MARKING_MIN_CONF=0.85`

9. **Testing/CI strategy (pytest + Django checks)**
   - Unit tests for token-box extraction and ROI coordinate remap.
   - Unit tests for integration helper contract and confidence threshold behavior.
   - Integration tests for accession-card and specimen-list hooks ensuring corrected value reaches QC persistence paths.
   - CI expectations: `pytest/pytest-django`, coverage target `>=90%`, `makemigrations --check`, and docs lint/build checks appropriate for Markdown docs (no MkDocs build).

10. **Docs, rollout, and PR hygiene**
   - Update docs in `/docs/development`, `/docs/admin`, `/docs/user` with feature flags and troubleshooting.
   - Update `CHANGELOG.md`.
   - Roll out behind feature flags; enable on staging first, verify sample pages and rollback path.
   - Keep PR title/body updated with latest implemented scope as commits evolve.

### New module file tree

```text
app/cms/ocr_boxes/
  __init__.py
  base.py
  tesseract_boxes.py
  paddle_boxes.py          # optional implementation
  service.py

app/cms/tooth_markings/
  integration.py
```

### URLs & CBVs/APIs/templates note
- This feature is service-layer focused; no new public URLs are required for Phase 1.
- Optional debug management command output can link from admin docs later.
- If any QC UI enhancements are added, extend existing templates with semantic HTML5 landmarks and current W3.CSS/Font Awesome conventions via base template inheritance.

### Permissions/auth/admin/history/filtering note
- Reuse existing permissions (e.g., specimen list review/approve permissions).
- Ensure any new model fields appear in admin list/detail where useful.
- Register `history` tracking impact for changed models already under `django-simple-history`.
- Continue use of existing list filters/pagination (`django-filter`) on review queues; no breaking filter changes.

### Install/deploy notes
- Python dep: `pytesseract` in `app/requirements.txt`.
- System dep on Linux hosts/containers: `tesseract-ocr` binary and language packs as needed.
- Default CPU-only deployment path; no CUDA assumptions.

### Known limitations / next steps
- Phase 1 uses token-pattern matching without per-row geometric linkage, so ambiguous repeated tokens may be replaced in order rather than exact row mapping.
- Bounding boxes are approximate and OCR-noise-sensitive.
- Next iteration: ROI detection for element field (template-based) and per-row segmentation for specimen-list tables.

---

## 3️⃣ Tasks (JSON)

```json
{
  "epic": "tooth-marking-ocr-integration",
  "tasks": [
    {
      "id": "TM-001",
      "title": "Create OCR box abstraction and TokenBox dataclass",
      "type": "backend",
      "paths": [
        "app/cms/ocr_boxes/__init__.py",
        "app/cms/ocr_boxes/base.py",
        "app/cms/ocr_boxes/service.py"
      ],
      "depends_on": [],
      "acceptance_criteria": [
        "Public API get_token_boxes(image, roi=None) exists.",
        "Public API get_token_crops(image, token_boxes) exists.",
        "TokenBox includes text/conf/bbox/token_id and optional line_id/block_id."
      ]
    },
    {
      "id": "TM-002",
      "title": "Implement Tesseract word-box backend with ROI remap",
      "type": "backend",
      "paths": [
        "app/cms/ocr_boxes/tesseract_boxes.py",
        "app/requirements.txt",
        "docs/development/*.md"
      ],
      "depends_on": [
        "TM-001"
      ],
      "acceptance_criteria": [
        "Engine returns non-empty boxes on known test image.",
        "ROI OCR returns boxes in full-page coordinates.",
        "Missing tesseract binary is handled gracefully when feature-flagged off."
      ]
    },
    {
      "id": "TM-003",
      "title": "Add optional PaddleOCR backend behind feature flag",
      "type": "backend",
      "paths": [
        "app/cms/ocr_boxes/paddle_boxes.py",
        "docs/development/*.md"
      ],
      "depends_on": [
        "TM-001"
      ],
      "acceptance_criteria": [
        "Backend is lazy-loaded only when OCR_BOX_ENGINE=paddle.",
        "Import/runtime errors fall back cleanly with warning logs."
      ]
    },
    {
      "id": "TM-004",
      "title": "Build tooth-marking integration helper service",
      "type": "backend",
      "paths": [
        "app/cms/tooth_markings/integration.py"
      ],
      "depends_on": [
        "TM-001",
        "TM-002"
      ],
      "acceptance_criteria": [
        "apply_tooth_marking_correction(page_image, element_text, roi=None) returns deterministic keys.",
        "Confidence threshold is configurable and enforced.",
        "Failures do not crash caller and preserve raw text."
      ]
    },
    {
      "id": "TM-005",
      "title": "Integrate correction into accession-card OCR flow before QC persistence",
      "type": "backend",
      "paths": [
        "app/cms/ocr_processing.py",
        "app/cms/models.py",
        "app/cms/migrations/*.py"
      ],
      "depends_on": [
        "TM-004"
      ],
      "acceptance_criteria": [
        "Raw and corrected element values are both persisted.",
        "QC-visible value uses corrected text when replacement confidence passes threshold.",
        "Detection metadata (token/conf/bbox/replacement_applied) is persisted."
      ]
    },
    {
      "id": "TM-006",
      "title": "Integrate correction into specimen-list extraction/approval path",
      "type": "backend",
      "paths": [
        "app/cms/ocr_processing.py",
        "app/cms/services/review_approval.py",
        "app/cms/models.py",
        "app/cms/migrations/*.py"
      ],
      "depends_on": [
        "TM-004"
      ],
      "acceptance_criteria": [
        "Specimen list element text is corrected before NatureOfSpecimen persistence.",
        "Row candidate data keeps raw + corrected + detections.",
        "Phase 1 works without per-row ROI segmentation."
      ]
    },
    {
      "id": "TM-007",
      "title": "Add tests for OCR boxes and integration hooks",
      "type": "test",
      "paths": [
        "app/cms/tests/test_ocr_boxes.py",
        "app/cms/tests/test_tooth_marking_integration.py",
        "app/cms/tests/test_specimen_list_*",
        "app/cms/tests.py"
      ],
      "depends_on": [
        "TM-002",
        "TM-004",
        "TM-005",
        "TM-006"
      ],
      "acceptance_criteria": [
        "Unit tests verify non-empty token boxes and ROI coordinate mapping.",
        "Integration tests verify corrected element reaches QC persistence paths.",
        "Coverage remains >=90%."
      ]
    },
    {
      "id": "TM-008",
      "title": "Add debug management command for manual verification",
      "type": "tooling",
      "paths": [
        "app/cms/management/commands/tooth_marking_debug.py",
        "docs/development/*.md"
      ],
      "depends_on": [
        "TM-004"
      ],
      "acceptance_criteria": [
        "Command prints raw vs corrected text and detection summary.",
        "Command can save overlay image with highlighted boxes."
      ]
    },
    {
      "id": "TM-009",
      "title": "Admin/QC surfacing and documentation updates",
      "type": "docs-admin",
      "paths": [
        "app/cms/admin.py",
        "app/templates/cms/*.html",
        "docs/user/*.md",
        "docs/admin/*.md",
        "docs/development/*.md",
        "CHANGELOG.md"
      ],
      "depends_on": [
        "TM-005",
        "TM-006"
      ],
      "acceptance_criteria": [
        "QC reviewers can inspect raw vs corrected element and detections.",
        "Docs explain feature flags, dependencies, and fallback behavior.",
        "Changelog entry added."
      ]
    }
  ]
}
```

---

## 4️⃣ Risks & Mitigations

- **Auth/permission risk**: New correction metadata could be exposed to unauthorized users in review UIs.
  - *Mitigation*: reuse existing review permission checks; avoid new unauthenticated endpoints.

- **Migration/data risk**: Adding raw/corrected/detection fields may produce null/default inconsistencies.
  - *Mitigation*: additive nullable fields first; data backfill optional and idempotent; migration dry-run in staging.

- **Data loss prevention**: Overwriting element text could remove OCR provenance.
  - *Mitigation*: always preserve raw text and store replacement metadata with confidence.

- **Performance risk**: Running extra OCR for boxes on each page can increase latency.
  - *Mitigation*: feature flags, optional ROI, per-page caching of token boxes, and selective invocation only when suspect tokens exist.

- **Accessibility risk**: If QC UI gets new panels, they may be visually clear but not screen-reader friendly.
  - *Mitigation*: semantic HTML5 regions, table headers, labels, keyboard focus order, and WCAG AA contrast checks.

- **Localization risk**: New labels/messages may bypass i18n.
  - *Mitigation*: wrap new user-facing strings in gettext and keep docs/user language clear.

- **Dependency vulnerability risk**: OCR dependencies may increase CVE surface area.
  - *Mitigation*: pin `pytesseract` version, monitor advisories, keep Paddle optional.

- **Rollback risk**: Incorrect rewrites might affect downstream QC/import quality.
  - *Mitigation*: feature flags to disable correction instantly; preserve raw values; rollback migration plan documented.

---

## 5️⃣ Out-of-Scope

- Full OCR pipeline rewrite or replacement of OpenAI OCR path.
- Robust per-row geometric segmentation for specimen-list tables.
- Automatic field-layout template detection for every accession card variant.
- GPU-dependent OCR deployment assumptions.
- Building a separate analytics dashboard for correction quality (deferred).

---

## 6️⃣ Definition of Done ✅

- [ ] Acceptance criteria from sections B–F are implemented and validated.
- [ ] Unit + integration tests are green (`pytest/pytest-django`) with coverage `>=90%`.
- [ ] Migrations are generated/applied/checked (`makemigrations --check`, migrate on staging).
- [ ] Admin integration is updated where needed.
- [ ] `django-simple-history` behavior is verified for changed tracked models.
- [ ] `django-filter` review/list workflows remain functional.
- [ ] Any template changes are mobile-first, semantic HTML5, and aligned with project base styling conventions.
- [ ] New user-visible strings are wrapped for i18n.
- [ ] Requirements changes are justified and documented.
- [ ] Docs updated in `/docs/user`, `/docs/admin`, `/docs/development`, and `CHANGELOG.md`.
- [ ] CI pipeline is green (tests, coverage gate, migration check, docs checks).
- [ ] Staging verification completed with representative accession card + specimen-list samples.
- [ ] Feature demo completed (debug command and reviewer walkthrough).
- [ ] Rollback plan confirmed (flags + migration reversibility + operational playbook).
