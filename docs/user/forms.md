# CMS Forms Refresher

The collections CMS now presents every create/edit flow inside a consistent W3.CSS card. Use this guide to understand what to expect and how to troubleshoot validation issues.

## Shared layout

- Each form page wraps the content in a `<main>` landmark with a descriptive heading such as “New Preparation” or “Edit Drawer”.
- Primary actions use W3.CSS buttons with Font Awesome icons (for example, the floppy disk icon on “Save accession”). Secondary navigation, such as “Back to accessions”, appears directly beneath the card using white bordered buttons.
- Help text and dynamic hints (e.g., “25 accession numbers available”) render immediately beneath the related field.

## Required fields and errors

- Required inputs display a red asterisk and a hidden “Required field” label for screen readers.
- When validation fails, the affected fields render with `aria-invalid="true"`, inline error messages, and the card shows a red alert banner summarising non-field errors.
- Keyboard users can tab through labels and inputs without encountering layout shifts; the card maintains a vertical flow without tables.

## File uploads

- File upload forms (media attachments, preparation media, field slip imports) automatically switch to `multipart/form-data`. A brief description highlights supported file types.
- The import screen uses a standard W3 input instead of the former drag-and-drop panel to simplify accessibility and mobile uploads.

## Accessibility tips

- Every field label is associated with its input via the `for` attribute, and help/error text is connected with `aria-describedby` for screen readers.
- Use the browser’s “Skip to main content” feature to jump directly into the form card.

## Quick reminders

- Save buttons always sit at the bottom-right of the card; look for the coloured icon to confirm the action.
- The card title switches between “New …” and “Edit …” based on whether you are creating or updating a record.
- Back links return to the relevant list or detail page without discarding unsaved changes.
