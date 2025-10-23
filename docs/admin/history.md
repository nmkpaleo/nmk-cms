# CMS History Views

The CMS exposes audit history in two places: model detail pages and the dedicated Media QC history view. Both now rely on shared W3.CSS tables with semantic markup so administrators can quickly scan changes.

## Detail page change logs

- Drawer registers, preparations, and storage areas render the same `history_table.html` partial. Each row includes an icon for the action (create/update/delete), the timestamp, the user, and a list of field-level changes.
- Empty states show a grey “No changes logged” message to avoid blank panels.
- The table caption is customised per page to improve screen reader context; captions appear above the table in muted text.

## Media QC history page

- Accessible from **QC History** in the global navigation or by following the “Open full history” links in the QC wizard.
- The header summarises the active media filter and exposes a “Show all history” reset link.
- Filters:
  - **Media UUID or filename** — accepts a partial UUID or filename to narrow the list.
  - **Change type** — dropdown of QC log categories (status, OCR data, rows rearranged).
  - Both filters use GET parameters so URLs are shareable; the “Clear filters” link resets to defaults.
- The history table includes the linked media label, change metadata, JSON diffs (old/new values), and inline discussion comments.
- Pagination buttons follow the same W3 bar component as list views and preserve current filters via query-string updates.

## Tips

- Because all history tables are partial-driven, avoid reintroducing bespoke markup when adding new audited models—include `cms/history_table.html` and ensure the view passes `history_entries` from `build_history_entries`.
- For QC history customisations, extend the context in `MediaQCHistoryView` so the filter form stays in sync with available change types.
