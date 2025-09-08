# Places (Admin)

Administrators can manage places that describe regions, sites, collecting areas or squares. Places are linked to a locality and may reference another place as a part of, synonym or abbreviation. Each place stores its higher geography path and lists any lower geography entries that are part of it.

Collection managers can add and edit places and manage their relationships, but only superusers may delete them.

The CMS interface also provides a **Places** section in the navigation menu where entries can be filtered by name, type or locality before viewing or editing details.

## Adding or Editing a Place
1. Log in to the admin site.
2. Select **Places** from the sidebar.
3. Use **Add Place** to create a new entry or choose an existing one to edit.
4. Specify the locality, name and place type.
5. Optionally choose a related place and set the relation type. The related place must belong to the same locality and a higher-level place cannot be set as part of one of its own descendants.
6. Save the entry. The higher geography path is calculated automatically and recorded in the log.

## Importing and Exporting
1. From the **Places** changelist, use **Import** or **Export** for bulk operations.
2. CSV files include columns for locality, name, place type, related place and relation type.
3. Place type values must be one of `Region`, `Site`, `CollectingArea` or `square` and relation type values must be `partOf`, `synonym` or `abbreviation`. Related places must share the same locality and circular hierarchies are not allowed.
4. After uploading, review the preview and confirm to apply the changes. Rows that violate these rules will be rejected with a clear error message.

## Viewing Change Logs
1. In the admin list, select a place.
2. Scroll to the history section to review past edits.
