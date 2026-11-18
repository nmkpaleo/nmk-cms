# Identifications

## Importing and Exporting

Use the **Import** and **Export** buttons on the Identifications admin changelist. Exports include each Identification's `id` and `taxon_verbatim`.

The `id` column is required in import files and identifies which Identification to update. A row with a blank `id` creates a new Identification; a file without an `id` column is rejected. Include `taxon_verbatim` when creating a row because it is required to validate the Identification.

The collection, specimen prefix, specimen number, and specimen suffix columns continue to identify the accession row associated with each Identification.
