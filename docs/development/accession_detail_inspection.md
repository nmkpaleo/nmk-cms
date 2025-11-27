# Accession detail template inspection (Task T1)

## View context
- `AccessionDetailView` (`app/cms/views.py`) supplies the template with `related_fieldslips`, `references`, `geologies`, `comments`, and `accession_rows` derived from the `Accession` instance and related querysets filtered through `prefetch_accession_related`.
- Additional context flags: `can_edit_accession_rows` (true for superusers or collection managers), `specimen_table_empty_colspan`, `taxonomy_map` data, identification summaries, and an `AccessionFieldSlipForm` for linking existing field slips.

## Comments section
- Located in `app/cms/templates/cms/accession_detail.html` under a `<section>` with `aria-labelledby="accession-comments-heading"`.
- Always rendered; the add-comment button is available only to authenticated users in the "Collection Managers" group. Table columns: Subject, Comment, Comment by, and Status. Falls back to an empty-state paragraph when no comments exist.

## References section
- Rendered from `app/cms/templates/cms/partials/accession_preview_panel.html` inside a lower-area section. Header shows a book icon and "References" label.
- Add-reference button appears for authenticated users in the "Collection Managers" group when not in preview mode.
- Table columns: Year, First author, Title, Page(s), with a footer count and an empty-state paragraph if no references are linked.

## Related layout considerations
- The accession preview panel also handles geology, accession rows, field slip links, identifications, and media; comments are outside this partial but share the lower-area layout on the detail page.
- Templates extend `base_generic.html` and use W3.CSS classes and Font Awesome icons for section headers and actions.
