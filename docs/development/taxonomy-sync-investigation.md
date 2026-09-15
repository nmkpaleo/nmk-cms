# NOW taxonomy sync investigation

Investigated on 15 September 2026. No application database was changed.

## Source comparison

The configured URLs in the local `.env` point to the NOW-Data main branch.
GitHub file history identifies these as the latest two revisions of both exports:

- [18 June 2026, b3f11c4](https://github.com/nowcommunity/NOW-Data/commit/b3f11c4f424bb6448bd82293c0043f4d50ae7c3c)
- [20 February 2026, a9318ac](https://github.com/nowcommunity/NOW-Data/commit/a9318ac101809b9d3473882897ba323160e61685)

Both versions have the same column headers. After the production parser excludes
subclass/suborder and deduplicates generated external IDs:

| Records | February | June | Added IDs | Removed IDs | Shared IDs with content changes excluding timestamp |
| --- | ---: | ---: | ---: | ---: | ---: |
| Accepted taxa | 18,239 | 18,257 | 155 | 137 | 567 |
| Synonyms | 1,254 | 1,405 | 157 | 6 | 61 |

Every shared record has a changed `STG_TIME_STAMP`. The service includes that
timestamp in updates, so update counts include records whose taxonomy is unchanged.

## Reproduced preview results

The actual parser, record construction, and preview methods from
`app/cms/taxonomy/sync.py` were executed with downloaded, commit-pinned TSV files.
An in-memory stand-in supplied existing Taxon objects and the filtered query;
this exercises matching logic without writing a database or running `_apply()`.

| Baseline and incoming data | Creates | Updates | Deactivations | Issues |
| --- | ---: | ---: | ---: | ---: |
| February NOW records, February export again | 0 | 0 | 0 | 0 |
| February NOW records, June export | 307 | 19,355 | 143 | 0 |
| February records labelled LEGACY, June export | 19,662 | 0 | 0 | 0 |

### Likely explanation for all creates

`_build_preview()` loads only records with `external_source="NOW"`. Its fallback
matching by name, rank, and status also searches only that subset. Migration 0065
assigned the default `LEGACY` source to existing records; it did not identify or
convert earlier NOW imports. The model still defaults to `LEGACY`.

Consequently, an existing catalogue of LEGACY-labelled taxa is invisible to this
sync, even if its names match the export exactly. A missing or incomplete previous
NOW import can also produce creates. The source comparison itself does not explain
an all-create preview against a complete February NOW import.

To confirm on the database serving the affected page, run these read-only queries:

```sql
SELECT external_source, status, COUNT(*) AS records
FROM cms_taxon
GROUP BY external_source, status;

SELECT external_source, COUNT(*) AS missing_external_ids
FROM cms_taxon
WHERE external_id IS NULL OR external_id = ''
GROUP BY external_source;
```

The local SQLite file has no taxonomy tables and no Compose services are running,
so the affected database's labels and import history could not be verified.
Do not relabel all LEGACY records indiscriminately: their provenance and ambiguous
name matches need checking before any migration adopts them as NOW records.

### Confirmed separate defect: update plus deactivation

When fallback matching finds an existing row with an old external ID, the preview
updates that ID. Deactivation still checks the row's original ID against the
incoming IDs, so it can also deactivate the same row.

The real source comparison contains five synonyms affected by this: their accepted
names changed, which changed their generated synonym IDs, while fallback matching
correctly found their existing rows. Thus 143 reported deactivations include five
rows also scheduled for update; only 138 unmatched previous rows remain.

An isolated old-ID example also produced one update and one deactivation for the
same object. A fix should track matched existing rows and exclude them from
deactivation, with a regression test covering synonym reassignment.

## Initial investigation validation limits

This was a read-only parser and preview investigation, not a database integration
test. The existing pytest suite could not start because the available Python
environment has no pytest installation. Database constraints and apply behavior
were not exercised. Application code was left unchanged.

See [sync architecture](taxonomy-sync.md) for the current workflow.


## Fix: preserve matched rows during deactivation

The preview now tracks matched database primary keys for accepted taxa and
synonyms. Rows matched through the fallback keep their active status even when
an update replaces their external ID. Missing, unmatched rows still deactivate.

Repeating the real February-to-June comparison with the fix produces 307 creates,
19,355 updates, and **138 deactivations**. The five reassigned synonyms are no
longer scheduled for deactivation. The LEGACY matching behavior is unchanged.

Regression tests cover accepted-taxon ID replacement and synonym reassignment,
including preview counts, database apply, preservation of the primary key and
active status, deactivation of an unmatched row, and an unchanged repeat preview.


Fix validation: all five tests in `app/cms/tests/test_sync_now.py` pass with
Django 5.2.16 and SQLite, including both new database regression cases. Tests ran
in an isolated Python 3.12 environment with `DEBUG=0`; Windows-inapplicable
server/debug dependencies were omitted. The full application suite was not run.
