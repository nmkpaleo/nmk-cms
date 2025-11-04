# Localities (Admin)

Administrators can manage locality codes through the Django admin interface.

## Adding or Editing a Locality
1. Log in to the admin site.
2. Select **Localities** from the sidebar.
3. Use **Add Locality** to create a new entry or choose an existing one to edit.
4. Enter the two-letter abbreviation, locality name, and select one or more geological time values (Miocene, Pliocene, Pleistocene, Holocene). Stored values keep the abbreviations, but the interface displays the full names everywhere in the CMS.
5. Save the entry. Changes are recorded in the log and tracked by django-simple-history.

## Searching and Filtering
- The changelist exposes a **Geological time** filter that narrows results to localities containing a selected time period.
- Standard search looks through abbreviations and names. Entering either a geological time abbreviation or its label (for example, `Pi` or `Pliocene`) will also return matching localities.

## Importing and Exporting
1. From the **Localities** changelist, use **Import** or **Export** for bulk operations.
2. CSV files include the `geological_times` column. Exports list geological time names joined with `/` (for example, `Miocene/Pliocene`). Imports accept either the abbreviations (`M/Pi`) or the labels (`Miocene/Pliocene`).
3. After uploading, review the preview and confirm to apply the changes. Invalid geological time values trigger a validation error before any rows are saved.

## Viewing Change Logs
1. In the admin list, select a locality.
2. Scroll to the history section to see past edits, including geological time changes.
