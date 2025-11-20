# Change Log Template Audit

This audit catalogs templates that render Change log sections and the Django views providing their context. The sections now live inside reusable tabs rendered by `cms/partials/tabs.html`.

## Findings

### Drawer register detail
- **Template:** `app/cms/templates/cms/drawerregister_detail.html`
- **Tabs:** `cms/tabs/drawerregister_details.html` and `cms/tabs/drawerregister_history.html` registered via `tab_config` in the view.
- **View:** `DrawerRegisterDetailView` (`app/cms/views.py`) using `HistoryTabContextMixin` to supply tab metadata and `history_entries`.
- **History rendering:** `cms/tabs/drawerregister_history.html` embeds `cms/history_table.html` inside the **Change log** tab with table ID `drawer-history-table` and localized caption/empty message.

### Storage detail
- **Template:** `app/cms/templates/cms/storage_detail.html`
- **Tabs:** `cms/tabs/storage_details.html` and `cms/tabs/storage_history.html` registered via `tab_config` in the view.
- **View:** `StorageDetailView` (`app/cms/views.py`) using `HistoryTabContextMixin` to supply tab metadata, history entries, and specimen pagination.
- **History rendering:** `cms/tabs/storage_history.html` embeds `cms/history_table.html` inside the **Change log** tab with table ID `storage-history-table` and localized caption/empty message.

## Maintenance tips
- Keep tab slugs in sync between `tab_config` and the `tabs.html` partial so button IDs and tabpanel IDs remain accessible.
- Preserve existing history context (``history_entries``) and i18n strings when adjusting the Change log tab templates.
