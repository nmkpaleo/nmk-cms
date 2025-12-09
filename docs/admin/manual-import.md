# Manual QC Import

Manual QC imports create accessions, identifications, and related records from spreadsheet rows that reference images in `uploads/manual_qc/`.

## Prerequisites
- Ensure scans were uploaded via **Upload scans** so manual QC JPEGs land in `uploads/manual_qc/` and create corresponding Media entries.
- Prepare the manual QC spreadsheet with one row per specimen and include the taxonomy columns listed below.

## Taxonomy mapping
Manual imports derive `Identification.taxon_verbatim` from the lowest taxonomic value provided in the spreadsheet. Qualifier tokens are preserved separately in `identification_qualifier` while the verbatim taxon text is stored in `verbatim_identification`.

| Column order (highest → lowest) | Purpose |
| --- | --- |
| `family`, `subfamily`, `tribe` | Used when genus/species are absent; the lowest non-empty value becomes `taxon_verbatim`. Qualifiers such as `cf.` and `aff.` are detected and saved to `identification_qualifier`. |
| `genus`, `species` | Preferred lowest-level values. When both are present, they are combined (e.g., `Genus species`). Qualifiers on either value (e.g., `cf.`) are preserved in `identification_qualifier`. |
| `taxon` | Fallback when no other taxonomy columns are supplied. |

Additional behaviors:
- `taxon_verbatim` always captures the lowest provided taxon (e.g., `Parapapio` from `Cercopithecidae | Papionini cf. Parapapio`).
- The qualifier is stored separately (`identification_qualifier` = `cf.` in the example above).
- The field slip’s verbatim taxon string is used for `verbatim_identification`; if absent, the synthesized taxonomy value is reused.
- Rows without any taxonomy values do not create identifications and surface validation errors until taxonomy is supplied.
- Spreadsheet taxonomy columns are distinct from the pipe-delimited verbatim taxon saved on the field slip; the latter remains unchanged and only feeds `verbatim_identification`.

## Troubleshooting
- If identifications fail with “Provide the lowest taxon for this identification,” confirm that at least one taxonomy column is populated. The import expects `taxon_verbatim` to be derived from those columns rather than left blank.
- Verify that manual QC media files are accessible under `/media/uploads/manual_qc/` so imported accessions can display previews.
