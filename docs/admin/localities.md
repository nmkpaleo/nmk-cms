# Localities (Admin)

Administrators can manage locality codes through the Django admin interface.

## Adding or Editing a Locality
1. Log in to the admin site.
2. Select **Localities** from the sidebar.
3. Use **Add Locality** to create a new entry or choose an existing one to edit.
4. Enter the two-letter abbreviation, locality name, and select one or more geological time abbreviations (M, Pi, Pe, H).
5. Save the entry. Changes are recorded in the log and tracked by django-simple-history.

## Importing and Exporting
1. From the **Localities** changelist, use **Import** or **Export** for bulk operations.
2. CSV files now include the `geological_times` column. Values should be slash-separated abbreviations (for example `M/Pi`).
3. After uploading, review the preview and confirm to apply the changes. Invalid geological time codes will raise an error during import.

## Viewing Change Logs
1. In the admin list, select a locality.
2. Scroll to the history section to see past edits, including geological time changes.
