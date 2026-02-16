# Tooth Marking CPU Dependency Upgrade Plan (Torch 2.8+)

## 1) Assumptions & Scope

### Django-specific assumptions
- Runtime remains Django 5.2.11 on Python 3.10 (per current Docker image), MySQL backend, and existing app loading patterns in `cms`.
- Tooth-marking inference is an optional CPU-only path installed from `app/requirements-tooth-marking-cpu.txt` and should stay opt-in.
- No model/schema changes are expected from a pure ML dependency bump, so no Django migrations should be required unless code adjustments become necessary.
- `django-simple-history` and `django-filter` behavior should be unaffected by the dependency update but still validated via regression tests because inference output is persisted into JSON fields.

### Apps to modify or create
- **Primary app impacted:** `app/cms/tooth_markings/` (model loading, preprocessing, prediction compatibility).
- **Likely touchpoints for validation only:**
  - `app/cms/ocr_processing.py`
  - `app/cms/services/review_approval.py`
  - `app/cms/management/commands/tooth_marking_debug.py`
  - existing test modules under `app/cms/tests/` and `tests/cms/`
- **No new Django app** should be created.

### Reused vs new components
- **Reuse:** Existing `correct_element_text`, `apply_tooth_marking_correction`, review-approval hooks, debug command, and persisted `tooth_marking_detections` JSON structures.
- **Net-new (only if needed):** Small compatibility helper(s) in `cms.tooth_markings` for Torch/Torchvision API drift and deterministic probability extraction.
- **No new models/forms/views** expected for this feature.

### Required packages (prefer existing)
- Target upgrades in `app/requirements-tooth-marking-cpu.txt`:
  - `torch==2.8.0+cpu` (or latest validated >=2.8.0)
  - matching `torchvision` version from official compatibility matrix (expected line: `0.23.x+cpu` for Torch 2.8 family; validate before merge)
- Keep existing requirements in `app/requirements.txt` unchanged unless transitive constraints force a change.
- Because the PyTorch CPU index was not reachable in this environment, the upgrade is **not implementation-ready to merge without CI validation in a network context that can reach `https://download.pytorch.org/whl/cpu`**.

## 2) High-Level Plan (5–12 steps)

1. **Baseline and compatibility discovery**
   - Confirm Python 3.10 support for Torch 2.8+ CPU wheels and the exact supported `torchvision` pairing.
   - Validate installability with pip dry-run from the CPU index in CI (or trusted build runner).

2. **Dependency update proposal**
   - Prepare a focused requirements patch in `app/requirements-tooth-marking-cpu.txt` only.
   - If and only if install/resolve succeeds, keep updated pins; otherwise revert and retain current `2.5.1+cpu`.

3. **Code compatibility verification in tooth-marking module**
   - Review `torch.load`, tensor operations, `torch.inference_mode`, and torchvision transforms for behavior changes.
   - Add minimal adapter/refactor only where needed to preserve deterministic output contracts.

4. **URL/CBV/API impact review (no new endpoints expected)**
   - Verify existing OCR/review flows still call inference helpers identically.
   - Ensure no behavioral regression in existing class-based review/admin pages.

5. **Forms/serializers/templates impact review**
   - Validate no template or form changes are required; if any related UX note is needed, keep templates extending `base_generic.html` with semantic HTML5 landmarks and existing W3.CSS/Font Awesome conventions.

6. **Filters/pagination/permissions/auth checks**
   - Run regression around review flows that persist inference output to ensure `django-filter` list pages and auth-protected workflows remain unchanged.
   - Confirm no changes are needed to `django-allauth` flows or permission rules.

7. **Admin and history integrity checks**
   - Validate admin rendering for `tooth_marking_detections` still works with upgraded inference outputs.
   - Verify `django-simple-history` snapshots remain stable and serializable.

8. **Testing and quality gates (Django 5.2/MySQL aware)**
   - Run `pytest`/`pytest-django` targeted suites + full relevant regression paths.
   - Enforce coverage >= 90% for changed scope.
   - Run migration checks (`makemigrations --check`) even if none expected.
   - Run docs lint/build steps used by this repository (skip any MkDocs step by policy).

9. **Docs/changelog and automation hygiene**
   - Update `CHANGELOG.md` and relevant docs in `/docs/development`, `/docs/admin`, `/docs/user` only if behavior/install instructions changed.
   - If `app/requirements.txt` is edited, run `python docs/scripts/update_prompts.py`; if untouched, do not run for this task.
   - Keep user-facing docs free from internal file-line citations; use descriptive prose and relative links.

10. **Rollout, flags, and rollback**
   - Treat as a staged dependency rollout: first CI green, then staging smoke for OCR/review.
   - If inference confidence or runtime regresses, rollback by restoring prior torch/torchvision pins.
   - PR title/body must be updated as scope changes in later commits so it always reflects latest work.

## 3) Tasks (JSON)

```json
{
  "epic": "tooth-marking-torch-upgrade",
  "version": 1,
  "tasks": [
    {
      "id": "TM-001",
      "title": "Validate Torch 2.8+ CPU wheel feasibility",
      "description": "Verify availability and install compatibility of torch>=2.8.0+cpu and matching torchvision for Python 3.10 in CI/build environment that can access PyTorch CPU index.",
      "paths": [
        "app/requirements-tooth-marking-cpu.txt",
        "app/Dockerfile"
      ],
      "dependencies": [],
      "deliverables": [
        "Compatibility note with chosen torch/torchvision pair",
        "Decision: proceed or hold upgrade"
      ],
      "acceptance_criteria": [
        "pip resolution succeeds from CPU wheel index",
        "Python 3.10 compatibility confirmed"
      ],
      "estimate": "0.5d"
    },
    {
      "id": "TM-002",
      "title": "Apply dependency pin updates conditionally",
      "description": "Update optional tooth-marking requirements to torch>=2.8.0 only when feasibility checks pass; otherwise keep current pins unchanged.",
      "paths": [
        "app/requirements-tooth-marking-cpu.txt"
      ],
      "dependencies": [
        "TM-001"
      ],
      "deliverables": [
        "Updated or explicitly retained dependency pins",
        "Rationale in changelog/PR"
      ],
      "acceptance_criteria": [
        "No unresolved or conflicting dependency constraints",
        "Rationale documented when no update is applied"
      ],
      "estimate": "0.25d"
    },
    {
      "id": "TM-003",
      "title": "Audit and patch tooth-marking runtime compatibility",
      "description": "Review inference utilities for any Torch/Torchvision API or behavior changes and add minimal compatibility updates if required.",
      "paths": [
        "app/cms/tooth_markings/models.py",
        "app/cms/tooth_markings/preprocess.py",
        "app/cms/tooth_markings/predict.py",
        "app/cms/tooth_markings/service.py",
        "app/cms/tooth_markings/integration.py"
      ],
      "dependencies": [
        "TM-002"
      ],
      "deliverables": [
        "Compatibility-safe inference path",
        "No contract changes to correction payloads"
      ],
      "acceptance_criteria": [
        "Inference API output schema unchanged",
        "Deterministic behavior preserved for existing tests"
      ],
      "estimate": "1d"
    },
    {
      "id": "TM-004",
      "title": "Regression validation across OCR/review/admin flows",
      "description": "Validate downstream integration points that consume tooth-marking output without introducing new models/forms/views.",
      "paths": [
        "app/cms/ocr_processing.py",
        "app/cms/services/review_approval.py",
        "app/cms/management/commands/tooth_marking_debug.py",
        "app/cms/admin.py"
      ],
      "dependencies": [
        "TM-003"
      ],
      "deliverables": [
        "Verified review pipeline behavior",
        "Verified admin/history rendering"
      ],
      "acceptance_criteria": [
        "No auth/permission regressions",
        "django-simple-history entries remain valid"
      ],
      "estimate": "0.5d"
    },
    {
      "id": "TM-005",
      "title": "Testing and CI hardening",
      "description": "Execute pytest/pytest-django suites, enforce coverage threshold, run migration checks, and run docs checks that align with repository policy.",
      "paths": [
        "pytest.ini",
        "tests/",
        "app/cms/tests/",
        "docs/"
      ],
      "dependencies": [
        "TM-004"
      ],
      "deliverables": [
        "Green test run",
        "Coverage report >=90% for changed scope",
        "Migration check output"
      ],
      "acceptance_criteria": [
        "pytest and pytest-django checks pass",
        "makemigrations --check passes",
        "No MkDocs invocation"
      ],
      "estimate": "0.5d"
    },
    {
      "id": "TM-006",
      "title": "Documentation, changelog, rollout, and rollback prep",
      "description": "Update user/admin/development docs and changelog as needed, and define rollout + rollback steps for dependency update.",
      "paths": [
        "docs/development/",
        "docs/admin/",
        "docs/user/",
        "CHANGELOG.md"
      ],
      "dependencies": [
        "TM-005"
      ],
      "deliverables": [
        "Updated documentation in plain Markdown",
        "Rollback instructions",
        "PR title/body aligned with final scope"
      ],
      "acceptance_criteria": [
        "Docs are external-audience friendly (no internal code citations)",
        "Changelog updated",
        "Rollout and rollback steps documented"
      ],
      "estimate": "0.25d"
    }
  ]
}
```

## 4) Risks & Mitigations

- **Auth-flow risk (indirect):** OCR/review pages are permissioned; regressions may surface as blocked actions.
  - *Mitigation:* run authenticated regression tests for review approval and page-review flows.
- **Data migration/data-loss risk:** no schema changes planned, but output payload shape drift can impact persisted JSON.
  - *Mitigation:* lock output contract in tests and compare before/after payload keys.
- **Performance risk:** newer Torch CPU wheels may change inference latency/memory.
  - *Mitigation:* add staging benchmark sample set and set rollback threshold.
- **Accessibility risk:** not expected for dependency-only change; if template updates become necessary, enforce semantic landmarks and mobile-first behavior.
- **Localization risk:** if user-visible text changes in tooling/errors, wrap strings with gettext and verify locale extraction.
- **Dependency vulnerability/supply-chain risk:** new wheel versions may add CVE exposure or incompatible binaries.
  - *Mitigation:* run dependency scanning in CI and freeze exact validated versions.
- **Rollback risk:** failed rollout could impact OCR throughput.
  - *Mitigation:* one-commit pin rollback path (`torch`/`torchvision` revert) and staged deployment gates.

## 5) Out-of-Scope

- Re-training tooth-marking models or changing model artifacts.
- New UI/UX features unrelated to dependency compatibility.
- Introducing GPU/CUDA runtime paths.
- Refactoring unrelated OCR pipelines.
- Creating new Django apps.

## 6) Definition of Done ✅

- [ ] Acceptance criteria for this feature are satisfied.
- [ ] Unit/integration tests are green with coverage >= 90% for changed scope.
- [ ] `makemigrations --check` passes; migrations applied only if intentionally added.
- [ ] Admin integration verified for tooth-marking outputs.
- [ ] `django-simple-history` behavior verified.
- [ ] `django-filter` list/review pathways verified.
- [ ] Any touched templates remain mobile-first and semantic HTML5 landmark compliant.
- [ ] i18n strings wrapped with gettext for any new user-facing copy.
- [ ] Requirements changes are justified and documented.
- [ ] Docs updated in `/docs/user`, `/docs/admin`, `/docs/development`, plus `CHANGELOG.md` when applicable.
- [ ] CI is green (tests, coverage, migration checks, docs checks).
- [ ] Staging verification completed.
- [ ] Feature demo completed with stakeholders.
- [ ] Rollback plan confirmed and tested.
