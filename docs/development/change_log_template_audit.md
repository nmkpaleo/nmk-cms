# Change Log Template Audit

This audit catalogs templates that render Change log sections and the Django views providing their context. Use it when migrating the sections into tabbed layouts.

## Findings

### Drawer register detail
- **Template:** `app/cms/templates/cms/drawerregister_detail.html`
- **View:** `DrawerRegisterDetailView` (`app/cms/views.py`)
- **Context for Change log:** `history_entries = build_history_entries(self.object)` provided in `get_context_data`.
- **History rendering:** Includes `cms/history_table.html` with table ID `drawer-history-table` and localized caption/empty message.

### Storage detail
- **Template:** `app/cms/templates/cms/storage_detail.html`
- **View:** `StorageDetailView` (`app/cms/views.py`)
- **Context for Change log:** `history_entries = build_history_entries(self.object)` provided in `get_context_data` alongside pagination context for specimens.
- **History rendering:** Includes `cms/history_table.html` with table ID `storage-history-table` and localized caption/empty message.

## Next steps
- Use this inventory to target templates for refactoring into the shared tab component.
- Preserve existing history context (``history_entries``) and i18n strings when moving sections.
