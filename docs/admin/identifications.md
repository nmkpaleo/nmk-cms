# Identifications

## Importing and Exporting

Use the **Export** button on the Identifications admin changelist to download Identification-only fields, including each record's `id` and `taxon`.

The **Import** workflow offers separate resources for updating existing Identifications and creating new ones:

- **Update existing:** Include the Identification `id` and only Identification fields. The `taxon` column updates the authoritative verbatim taxon value. Blank or unknown IDs are rejected; this workflow cannot create records or change their accession row.
- **Create new:** Do not include an Identification `id`. Include collection, specimen prefix, specimen number, and specimen suffix to resolve the accession row. Exactly one matching row must exist. Include `taxon_verbatim`, which is required to validate the new Identification.
