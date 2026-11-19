# Identifications

## Importing and Exporting

Use the **Export** button on the Identifications admin changelist to download `id` and the Identification fields `verbatim_identification`, `taxon_verbatim`, `identification_qualifier`, and `identification_remarks`. These headers match the normal import/export field names.

The **Import** workflow offers separate resources for updating existing Identifications and creating new ones:

- **Update existing:** Include the Identification `id` and the four fields listed above. Blank or unknown IDs are rejected; this workflow cannot create records or change their accession row. The model's existing save behavior continues to synchronize `taxon` from `taxon_verbatim`.
- **Create new:** Do not include an Identification `id`. Include collection, specimen prefix, specimen number, and specimen suffix to resolve the accession row. Exactly one matching row must exist. Include `taxon_verbatim`, which is required to validate the new Identification.
