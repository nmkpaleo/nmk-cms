# Working with List Views

The collection management system renders list and search pages with a consistent W3.CSS-first layout. Each list view extends `base_generic.html`, which already loads W3.CSS, Font Awesome 6, and the shared pagination block.

## Layout basics

- **Semantic structure:** List pages wrap their content in `<main>` and `<section>` landmarks to aid assistive technologies. Filter panels sit inside an accordion panel immediately after the section header.
- **Responsive grid:** Header toolbars use `w3-row` and `w3-col` utilities so that buttons stack on mobile (`s12`) and align right on large screens (`l6`).
- **Tables:** Results tables rely on `w3-responsive` containers plus `w3-table-all w3-hoverable` classes for built-in zebra striping and hover states. Wide tables hide low-priority columns using `w3-hide-small` / `w3-hide-medium` classes, controlled by a “Show more” toggle.
- **Filters:** Filter forms render with `w3-row-padding` and `w3-margin-bottom` wrappers. Submit buttons use `w3-button w3-blue w3-round` and the reset links use `w3-button w3-gray w3-round` for contrast compliance.
- **Icons:** Page-level actions (e.g., “New Accession”, “New Place”) use Font Awesome icons (`fa-plus-circle`, `fa-filter`, etc.) to communicate meaning without relying on colour alone.

## Common interactions

1. **Toggle filters:** Click the “Show/Hide Filters” button to reveal the W3 accordion. The state persists per page load.
2. **Apply filters:** Enter filter values and press the blue “Apply Filters” button. Use the grey “Clear” button to reset all criteria.
3. **Pagination:** Pagination controls appear below the table via the shared block in `base_generic.html`. They render accessible previous/next buttons with icons and text labels.
   - Active filter selections now persist when you click **Previous** or **Next**.
   - This applies to list pages such as **Accessions** and **Localities**, including multi-select filters.
4. **Mobile controls:** On small screens, header actions stack vertically and tables scroll horizontally inside the `w3-responsive` wrapper.

## Filter persistence examples

- If you filter Accessions by organisation or specimen prefix, moving to page 2 keeps the same filtered set.
- If you filter Localities by multiple geological times, paging forward/back keeps all selected geological time values.

## Accessibility considerations

- All actionable buttons include `aria-label` attributes when the visible text is hidden on mobile.
- Table headers use `<th scope="col">` to provide explicit associations for screen readers.
- Empty states render as centred rows with descriptive text (e.g., “No field slips found.”) to avoid silent failures.

Refer to the following templates for canonical patterns:

- `app/cms/templates/cms/accession_list.html`
- `app/cms/templates/cms/fieldslip_list.html`
- `app/cms/templates/cms/storage_list.html`
