# Manual QC Import

Manual QC imports create accessions, identifications, and related records from spreadsheet rows that reference images in `uploads/manual_qc/`.

Manual QC imports create accessions, identifications, and related records from
spreadsheet rows that reference images in uploads/manual_qc/. The import
requires two kinds of files: JPEG media files and one tabular QC file. The QC
file can be a CSV (plain-text file) or an Excel workbook (.xlsx). A plain .txt
file is not supported unless it is saved as a comma-separated CSV file.

## Prerequisites
- Complete the manual QC outside the CMS.
- Name each image with digits only before the extension, for example 1.jpg and 2.jpg.
- Prepare one CSV or .xlsx file with one row per specimen. Its required id value
  must match the image filename without the extension: 1 matches 1.jpg.
- Include the taxonomy columns listed below when creating identifications.

## Upload the media and QC file

1. Log in with an account that has permission to import manual QC.
2. Open **Upload scans** and select the manually QC-checked JPEG files.
3. Click **Upload**. Matching files are moved to uploads/manual_qc/ and create Media records.
4. Open **Manual QC Import**.
5. In **Manual QC spreadsheet**, choose the CSV or .xlsx file and click **Import data**.
   For a plain-text source, save it as CSV first; it must have a header row including id.
6. Check the import summary and download the error report if any rows fail.

Example CSV (save this as a .csv file):

    id,collection_id,genus,species
    1,KNM,Parapapio,
    2,KNM,Australopithecus,afarensis

The import finds the JPEG by the id value, marks matched Media records as approved,
and creates related accession data. Separate 1.txt or 2.txt sidecar files are not
read by this importer; put the QC results into the CSV/Excel rows or retain the
text notes outside the CMS according to your record-keeping procedure.
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
