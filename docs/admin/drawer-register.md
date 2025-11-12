# Drawer Register (Admin)

Administrators can manage drawers and their scanning status through the Django admin interface.

## Adding or Editing a Drawer
1. Log in to the admin site.
2. Select **Drawer Registers** from the sidebar.
3. Use the **Add Drawer Register** button or select an existing entry to edit.
4. Provide a three-letter code, description, and any related localities or taxa.
5. When the scanning status is set to *In progress*, at least one scanning user must be selected.
6. Save the entry. Status and user changes are recorded in the log automatically.

## Importing and Exporting
1. From the **Drawer Registers** changelist, use the **Import** and **Export** buttons to bulk load or download entries.
2. CSV files use a semicolon (`;`) to separate multiple localities, taxa, or scanning users. Exported taxa values always use the primary taxon name stored on each `Taxon` record, which matches the value required for successful re-imports.
3. After uploading an import file, review the preview and confirm to apply the changes.

## Viewing Change Logs
1. In the admin list, select a drawer register.
2. Scroll to the **Drawer Register Logs** section to see a history of status and user changes.
