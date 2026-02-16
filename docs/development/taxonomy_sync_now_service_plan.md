# NOW Taxonomy Sync Service Plan

## 1️⃣ Assumptions & Scope
- Django 4.2 project with existing `apps.cms` application owning taxonomy logic; service additions will reside under `apps.cms.taxonomy`.
- `Taxon` and `TaxonomyImport` models from Task T1 already exist with required fields, constraints, and history tracking; no schema changes necessary here.
- Sync functionality will be implemented as pure Python services/utilities (no new models/forms/views) and exercised via Django admin actions in later tasks.
- No additional third-party packages required; rely on Python stdlib (`csv`, `dataclasses`, `typing`) and Django ORM.
- External NOW TSV endpoints reachable via HTTP; requests will use `urllib.request` or existing project HTTP helpers to avoid new dependencies.

## 2️⃣ High-Level Plan
1. **Service Module Setup**: Create `apps/cms/taxonomy/sync.py` providing orchestrating functions (`fetch_now_taxa`, `parse_now_tsv`, `build_diff`, `apply_diff`) and a high-level `sync_now_taxa` entry point returning diff summaries.
2. **Configuration Integration**: Read NOW URLs and deactivate flag from Django settings (`TAXON_NOW_ACCEPTED_URL`, `TAXON_NOW_SYNONYMS_URL`, `TAXON_SYNC_DEACTIVATE_MISSING`) with sensible defaults; validate presence before fetch.
3. **Data Fetching Layer**: Implement streaming download with timeout/error handling, capturing source version metadata (commit SHA/date) from TSV content.
4. **Parsing & Normalization**: Parse TSVs using `csv.DictReader`, normalizing whitespace/case for matching, building accepted and synonym dataclass records with deterministic external IDs.
5. **Diff Computation**: Compare parsed records against existing `Taxon` queryset to determine creates, updates, reactivations, deactivations, synonym link changes, and issues (e.g., missing accepted targets, rank mismatches) with reproducible ordering.
6. **Transactional Apply**: Wrap DB mutations in `transaction.atomic()`, performing bulk creates/updates, managing `is_active` toggles, synonym `accepted_taxon` relations, and logging results to `TaxonomyImport`; ensure idempotency by reusing external IDs and checking for no-op updates.
7. **Dry-run Support**: Allow consumers to request diff-only previews without DB writes; ensure apply path can reuse diff results for performance.
8. **Audit Logging**: Populate `TaxonomyImport` entries with counts, report payloads, source version, and success flag; expose helper to mark completion.
9. **Testing**: Implement pytest suite `apps/cms/tests/test_sync_now.py` with fixtures for sample TSV content, mocking HTTP calls, verifying parsing, diff accuracy, idempotent apply, synonym link behavior, and issue reporting.
10. **Documentation**: Update `/docs/development/taxonomy.md` with architecture overview of sync services, configuration settings, and extension notes.

## 3️⃣ Tasks (JSON)
[
  {
    "id": "T2.1",
    "title": "Create NOW sync service module",
    "summary": "Implement data fetching, parsing, diffing, and application utilities for NOW taxonomy TSVs.",
    "app": "apps.cms",
    "files_touched": [
      "app/cms/taxonomy/__init__.py",
      "app/cms/taxonomy/sync.py"
    ],
    "migrations": false,
    "settings_changes": [
      "settings var changes as needed (TAXON_NOW_ACCEPTED_URL, TAXON_NOW_SYNONYMS_URL, TAXON_SYNC_DEACTIVATE_MISSING)"
    ],
    "packages": [],
    "permissions": [],
    "acceptance_criteria": [
      "Functions fetch and parse NOW TSVs into normalized accepted and synonym records.",
      "Diff computation identifies creations, updates, deactivations, and issues deterministically.",
      "Apply routine runs inside a transaction, touching only changed rows, and is idempotent on repeated runs."
    ],
    "test_plan": [
      "pytest unit tests covering parsing accuracy, diff outputs, apply idempotency, synonym link enforcement, and issue reporting."
    ],
    "docs_touched": [
      "docs/development/taxonomy.md"
    ],
    "dependencies": [
      "T1"
    ],
    "estimate_hours": 8.0,
    "risk_level": "high",
    "priority": "high",
    "reviewer_notes": [
      "Ensure TSV streaming handles large files without excessive memory usage."
    ]
  },
  {
    "id": "T2.2",
    "title": "Add sync service tests and fixtures",
    "summary": "Author pytest coverage for NOW sync utilities including mocks for external HTTP sources.",
    "app": "apps.cms",
    "files_touched": [
      "app/cms/tests/test_sync_now.py"
    ],
    "migrations": false,
    "settings_changes": [],
    "packages": [],
    "permissions": [],
    "acceptance_criteria": [
      "Unit tests validate parsing, diff generation, apply idempotency, and issue handling for edge cases.",
      "HTTP calls are fully mocked, allowing offline deterministic test runs."
    ],
    "test_plan": [
      "pytest unit tests for sync service functions with multiple scenarios, including dry-run and apply flows."
    ],
    "docs_touched": [],
    "dependencies": [
      "T2.1"
    ],
    "estimate_hours": 6.0,
    "risk_level": "medium",
    "priority": "high",
    "reviewer_notes": [
      "Consider parametrized tests for rank/status transitions."
    ]
  },
  {
    "id": "T2.3",
    "title": "Document NOW sync service architecture",
    "summary": "Update developer documentation with guidance on service configuration and extension points.",
    "app": "docs",
    "files_touched": [
      "docs/development/taxonomy.md"
    ],
    "migrations": false,
    "settings_changes": [],
    "packages": [],
    "permissions": [],
    "acceptance_criteria": [
      "Documentation explains configuration variables, service flow, and troubleshooting tips."
    ],
    "test_plan": [
      "Docs build via CI."
    ],
    "docs_touched": [
      "docs/development/taxonomy.md",
      "CHANGELOG.md"
    ],
    "dependencies": [
      "T2.1"
    ],
    "estimate_hours": 2.0,
    "risk_level": "low",
    "priority": "medium",
    "reviewer_notes": []
  }
]

## 4️⃣ Risks & Mitigations
- **Auth/Permissions**: Service invoked by admin-only flows; ensure callers enforce `taxonomy.can_sync` permission and log acting user in `TaxonomyImport`.
- **Data Integrity**: Use `transaction.atomic()` and `select_for_update` to guard concurrent sync runs; perform validation before writes to prevent inconsistent synonyms.
- **Performance**: Stream TSV parsing to avoid loading entire files in memory; leverage bulk operations and minimal queryset evaluations.
- **Rollback Strategy**: Since no migrations, rollback involves reverting code and rerunning sync with previous dataset; maintain prior `TaxonomyImport` history for audit.
- **Accessibility & i18n**: Service layer has no UI components; downstream templates will ensure ARIA/i18n compliance.
- **Localization**: Log messages and exceptions use `_()` wrappers when surfaced to UI; data normalization is locale-agnostic.
- **Dependency Vulnerabilities**: No new packages; continue monitoring via existing tooling.

## 5️⃣ Out-of-Scope
- Automating scheduled syncs or background jobs.
- PBDB or non-mammal data sources.
- Admin UI components (buttons, previews) beyond service layer integration.
- Modifications to downstream search or API endpoints.

## 6️⃣ Definition of Done ✅
- Service functions deliver deterministic diff and transactional apply per acceptance criteria.
- Unit tests cover parsing, diffing, application, and edge cases with ≥90% coverage in new code.
- Configuration settings documented and validated.
- Code reviewed, merged, and deployed with monitoring plan; ability to rerun sync safely confirmed.
- Documentation updated in `/docs/development/taxonomy.md` (and CHANGELOG when code ships).
- CI green (lint, type-check, tests, docs) with mocks ensuring offline reliability.
