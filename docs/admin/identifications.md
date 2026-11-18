# Identifications

## Importing and Exporting

Use the **Export** button on the Identifications admin changelist to download `id` and these Identification fields: **Verbatim identification**, **Lowest identified taxon**, **Taxon Qualifier**, and **Remarks**.

The **Import** workflow offers separate resources for updating existing Identifications and creating new ones:

- **Update existing:** Include the Identification `id` and the four fields listed above. Blank or unknown IDs are rejected; this workflow cannot create records or change their accession row. The model's existing save behavior continues to synchronize `taxon` from **Lowest identified taxon**.
- **Create new:** Do not include an Identification `id`. Include collection, specimen prefix, specimen number, and specimen suffix to resolve the accession row. Exactly one matching row must exist. Include `taxon_verbatim`, which is required to validate the new Identification.
