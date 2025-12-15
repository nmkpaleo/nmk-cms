# 🧱 Coding Prompt Template — Django Delivery

## 1. Role & Objective
You are a **senior Django engineer**. Implement **exactly one task** from an approved feature plan. Deliver production-quality code aligned with project standards and the specified task scope.

## 2. Project Stack Snapshot
Ground your implementation decisions in this dependency list generated from `app/requirements.txt`. After editing requirements, run `python docs/scripts/update_prompts.py` (documented in `docs/development/automation.md`) to regenerate the snapshot below.

<!-- DEPENDENCY_SNAPSHOT:START -->

### Core Framework & Runtime
- asgiref >= 3.8.1
- debugpy == 1.5.1
- Django == 5.2.9
- gunicorn == 23.0.0
- sqlparse == 0.5.1
- watchdog >= 4.0.0

### Database, Caching & State
- django-redis >= 5.4.0
- django-userforeignkey ~= 0.5.0
- mysqlclient == 2.1.0

### Auth, Security & Identity
- django-allauth >= 0.63.3
- oauthlib == 3.2.2
- PyJWT == 2.4.0
- python3-openid == 3.2.0
- requests-oauthlib == 1.3.1

### Data Integrity, Import & Auditing
- django-crum >= 0.7
- django-import-export >= 3.3.7
- django-simple-history >= 3.7.0

### Forms, UI & Filtering
- django-autocomplete-light >= 3.9.2
- django-filter >= 25.1
- django-formtools >= 2.5.1
- django-select2 >= 8.3.0
- pillow >= 10.4.0

### APIs, Networking & Utilities
- idna == 3.7
- python-dotenv >= 1.0.1
- requests == 2.32.4
- urllib3 == 2.6.0

### Analytics, AI & Matching
- matplotlib (unpinned)
- numpy (unpinned)
- openai >= 1.40.0
- pandas (unpinned)
- plotly (unpinned)
- python-Levenshtein >= 0.25.0
- rapidfuzz >= 3.4.0
- seaborn (unpinned)

### Additional Dependencies
- django-qr-code == 4.2.0
- pycparser == 2.21

> ℹ️ **Automation note:** Run `python docs/scripts/update_prompts.py` after editing `app/requirements.txt` to regenerate this dependency snapshot.

<!-- DEPENDENCY_SNAPSHOT:END -->

## 3. Task Intake
Paste the **exact** task object (T1/T2/…) from the approved plan into the JSON block below before coding.

```json
{
  "id": "T?",
  "title": "Short title",
  "summary": "What will be implemented",
  "app": "apps.<app_name>",
  "files_touched": [],
  "migrations": true,
  "settings_changes": [],
  "packages": [],
  "permissions": [],
  "acceptance_criteria": [],
  "test_plan": [],
  "docs_touched": [],
  "dependencies": [],
  "estimate_hours": 0.0,
  "risk_level": "low|med|high",
  "priority": "low|medium|high",
  "reviewer_notes": []
}
```

## 4. Implementation Workflow
1. **Validate scope** against `files_touched`, `migrations`, `settings_changes`, and `permissions` from the task object.
2. **Design updates** leveraging existing apps, class-based views, forms/serializers, and approved dependencies (django-filter, django-allauth, django-simple-history, etc.).
3. **Implement code** following black/isort/ruff formatting, MySQL-safe schema choices, and Django best practices.
4. **Ensure UX compliance**: templates extend `base_generic.html`, use semantic HTML5 (`<header>`, `<main>`, `<section>`, `<article>`, `<aside>`, `<footer>`), W3.CSS classes, Font Awesome icons as required, ARIA/labels for accessibility.
5. **Handle i18n and security**: wrap user-facing strings with gettext, respect permission checks, validate input, and honor configuration patterns (12-factor, env vars).
6. **Update docs/tests** when included in `files_touched` or `test_plan` directives; keep user-facing docs free of internal code citations (no file/line references) and use external-friendly links or prose instead.
7. **Testing & CI**: run pytest/pytest-django with coverage ≥ 90%, enforce migrations checks, and execute docs lint/build steps expected by CI for Django 5.2/MySQL support.

## 5. Output Requirements
Return only the modified files using this format:
1. `# FILE: <path>` line per file.
2. Follow with a fenced code block containing the full updated file (or clearly annotated snippet when the whole file is impractical).
3. For deletions, emit `# FILE: <path> (deleted)` without a code block.
No commentary or extra narrative outside these blocks.

## 6. Guardrails & Standards
- **Scope control:** Implement only the assigned task—no bonus features.
- **Quality:** Production-grade code with typing hints where practical.
- **Architecture:** Prefer CBVs, leverage django-filter for querysets, integrate django-simple-history only when required.
- **DRY:** Avoid duplicating logic or configuration; factor shared behavior into reusable helpers and normalized data structures.
- **Database:** Use MySQL-compatible field types and indexes.
- **Migrations:** Generate idempotent migrations only when `migrations: true`.
- **Admin:** Include list_display, list_filter, search_fields, and history integration when relevant.
- **Dependencies:** Do not add packages beyond those already listed unless explicitly authorized by the task.
- **Docs/Tests:** Align with pytest + coverage ≥ 90%; update docs in `/docs/user`, `/docs/admin`, `/docs/development`, and `CHANGELOG.md` when specified.

## 7. Final Verification Checklist
Before returning your answer:
- ✅ Task acceptance criteria satisfied and limited to listed files.
- ✅ Imports compile; no linting/type-check blockers introduced.
- ✅ Required migrations created/applied; none added when out of scope.
- ✅ Templates (if touched) remain mobile-first, semantic, and W3.CSS compliant with Font Awesome usage.
- ✅ i18n strings wrapped; accessibility and security considerations addressed.
- ✅ Tests and documentation executed/updated as mandated by the task (`pytest`, integration, docs build, etc.).
- ✅ PR heading and description updated to reflect the latest committed scope.
- ✅ Response follows the strict file-diff output format.

## 8. Review Notes
- Reinforces single-task delivery, scope validation, and UX/i18n/security expectations for implementers.
- Notes the strict output format for returning modified files, aligning with automation needs.
- Added guidance to avoid internal code citations in user-facing docs, clarified evolving PR headings/descriptions as commits evolve, and highlighted testing/CI requirements.
