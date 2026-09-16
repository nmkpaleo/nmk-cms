# Taxonomy Sync Architecture

This document explains how the NOW taxonomy sync is implemented and how to extend or troubleshoot it during development.

## Overview

The sync feature ingests two TSV exports from the NOW-Data repository—`latest_taxonomy.tsv` for accepted taxa and `latest_taxonomy_synonyms.tsv` for synonyms. The pipeline:

1. Downloads the TSV files using configured environment variables.
2. Parses the rows into in-memory records (`AcceptedRecord` / `SynonymRecord`).
3. Restricts records to normalized local names from `Taxon`, identification text, and field-slip text, plus accepted targets required by matching synonyms. Existing NOW external IDs also retain their matching source records. Drawer links are covered by the existing `Taxon` records.
4. Compares that subset with existing `Taxon` rows across sources to produce a diff preview. Matched database rows are excluded from deactivation even if their external IDs change.
5. Applies each independent dependency group atomically, retaining successful groups and recording skipped groups in a `TaxonomyImport` audit row.

The UI uses `TaxonomySyncService` in `app/cms/taxonomy/combined.py`. GBIF response
validation lives in `gbif.py`; the shared diff/apply machinery remains in `sync.py`.
`NowTaxonomySyncService` remains available for NOW-only callers. All sync writers
populate the source-independent `Taxon.identity_key`; bulk writers must compute it
with `cms.taxon_identity.taxon_identity` when changing name/rank.

GBIF is queried only for locally recorded names. Exact matches establish the class:
NOW takes priority for Mammalia, GBIF for other classes and mammals missing in NOW.
Source transitions reuse the existing row. Apply also links resolvable identification
text and records the link changes in history. See the
[administrator guide](../admin/taxonomy-sync.md#source-selection-and-duplicate-prevention)
for migration and error-handling details.

## Key components

| Component | Purpose |
| --- | --- |
| `NowTaxonomySyncService` | Public API providing `preview()` and `sync(apply=True)` methods used by the Django admin workflow. |
| `SyncPreview` | Structured diff that lists accepted and synonym creates/updates, deactivations, and issues. |
| `TaxonomyImport` | Model logging each run with counts, issue context, and source version; tracked via `django-simple-history`. |
| `Taxon` model fields | Extended with NOW-specific metadata (`external_source`, `external_id`, `status`, `rank`, `source_version`, etc.) and constraints enforcing synonym relationships. |

## Configuration

Set the following environment variables (or Django settings in local overrides):

* `TAXON_NOW_ACCEPTED_URL` – HTTPS URL for `latest_taxonomy.tsv`.
* `TAXON_NOW_SYNONYMS_URL` – HTTPS URL for `latest_taxonomy_synonyms.tsv`.
* `TAXON_SYNC_DEACTIVATE_MISSING` – `true`/`false`; when true, NOW taxa missing from the export are marked inactive.

Configuration lives in standard settings files; keep secrets and URLs out of the codebase in line with 12-factor principles.

## Running the sync locally

1. Create a superuser with the `cms.can_sync` permission.
2. Export the environment variables above. For local testing you can point them to fixture files using `python -m http.server` or `file://` URLs supported by your environment.
3. Visit the Django admin, open the Taxon changelist, and trigger **Sync Taxa Now**.
4. Inspect the preview and apply the sync to populate NOW taxonomy data.

Alternatively, use the service directly from the shell:

```python
from cms.taxonomy.combined import TaxonomySyncService
service = TaxonomySyncService()
preview = service.preview()
result = service.sync(apply=True)
```

## Testing

Automated coverage lives in:

* `app/cms/tests/test_sync_now.py` – unit tests covering preview, apply, synonym linking, deactivation, and issue reporting. Remote HTTP calls are mocked via injectable request functions.
* `app/cms/tests/test_forms.py` and `app/cms/tests/test_filters.py` – verify downstream forms, filters, and widgets honour the new taxonomy schema.

Run the suite with:

```bash
pytest app/cms/tests/test_sync_now.py app/cms/tests/test_forms.py app/cms/tests/test_filters.py
```

All tests should pass with coverage ≥ 90%. Mock external requests in additional tests using the `http_get` injection pattern demonstrated in `test_sync_now.py`.

## Error handling

* Missing settings raise `RuntimeError` before any network calls.
* Network or parsing errors bubble up to the admin views; users see a translated error banner.
* Issues detected during preview are surfaced via `SyncIssue` entries and block automatic synonym creation.
* Apply groups connected taxa (synonyms and accepted targets, row identity, and source-ID transfers) into savepoints. Data errors roll back only that group; fatal failures roll back the request. Apply counts include successful groups only.

## Extending the service

* To add new external sources, create additional `ExternalSource` enum values and corresponding service classes following the NOW example.
* If the NOW schema changes, update the parser helpers (`_parse_accepted`, `_parse_synonyms`) and maintain the external ID format helpers in the same module.
* Any new metadata should be added to the `Taxon` model along with migrations and tests before adjusting the sync service.

## Observability

* Standard Django logging captures warnings for malformed rows and unresolved synonyms.
* Each import is stored in `TaxonomyImport` and viewable via the Django admin.
* Enable application performance monitoring around the sync views if you need more insight into run times (~100k rows expected to complete within 30 seconds).


## Reviewed preview apply

The UI posts a compressed, signed, user-bound snapshot (`taxonomy/snapshot.py`).
It contains the reviewed records and a hash of the local taxa, identification names
and links, and field-slip names. Apply verifies the signature, one-hour lifetime,
user, and current catalogue hash while locking existing taxa. It does not refetch
external sources. Modified, stale, or expired previews require a new preview.
Unexpected failures render a dedicated error page and are logged server-side.

Regression tests in `test_taxonomy_apply.py` cover partial success, database failures,
long authorship, dependent synonyms, snapshot validation, and the POST response.
