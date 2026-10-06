# Accession merges

Superusers and data administrators with `cms.can_merge_accession` can merge duplicate accessions from the Accession admin list.

Select the accessions, choose the accession to retain, and confirm the merge. The merge keeps an audit log, moves related records, merges rows with matching specimen suffixes, and preserves media links. Manual QC row matching is supported by the imported spreadsheet row identifier and unique media filename.

Source accessions are archived rather than deleted. They are hidden from normal lists and searches. Existing accession URLs and QR codes redirect to the retained accession.

Always use the preview/dry-run workflow against a database backup before processing a large import batch. Ambiguous row or media relationships should be reviewed before confirmation.

## Global Reference deduplication

Preview exact duplicate References with:

```text
python app/manage.py deduplicate_references
```

The command normalizes surrounding/repeated whitespace, keeps the oldest Reference as canonical, repoints Accession Reference and Identification relations, removes duplicate links, and deletes duplicate Reference records only when `--apply` is supplied:

```text
python app/manage.py deduplicate_references --apply
```

This operation is separate from the 220-record cleanup and should be reviewed from the dry-run output first.
