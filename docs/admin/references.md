# References (Admin)

Administrators can manage bibliographic references through the Django admin interface.

## Adding or Editing a Reference
1. Log in to the admin site.
2. Select **References** from the sidebar.
3. Use **Add Reference** or select an existing entry to edit.
4. Provide the title, first author, year and any optional fields.
5. Save the entry.

## Importing and Exporting
1. From the **References** changelist, use **Import** and **Export** for bulk operations.
2. CSV files include citation details such as title, author and year.
3. After uploading, review the preview and confirm to apply the changes.

## Splitting Citations
1. From the **References** changelist, select **Split References by |**.
2. Review the citations containing multiple non-empty parts separated by `|`.
3. Confirm to create one Reference for each part. Each part becomes that record's title, first author and citation.
4. A four-digit year in a part is used as that Reference's year; parts without a year keep the original Reference's year.
5. Accession-reference and identification links, including accession page details, are copied to each new record.

## Viewing Change Logs
1. In the admin list, select a reference.
2. Scroll to the history section for edit records.
