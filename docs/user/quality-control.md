# Quality Control

The quality control (QC) workflow is split into two stages:

1. **Intern review** – interns verify and tidy the OCR results captured for a
   media card. This includes correcting accession details, reordering rows to
   match the card layout, and ensuring specimen information is complete.
2. **Expert review** – once an intern submits the record, an expert receives the
   refined data and can finalise the accession.

This guide covers the intern-focused wizard that prepares a media item for the
expert review step.

## Accessing the intern QC wizard

- The wizard lives at `/qc/intern/<uuid>/`, where `<uuid>` is the media item's
  public identifier. You can copy this link from the QC queue or the media
  detail view.
- Only users in the **Interns** group can load the page. Others will receive a
  “403 – Forbidden” response.
- The form is read/write and will pre-populate from the existing
  `Media.ocr_data` JSON payload when available.

## Reviewing accession details

The first section mirrors the standard accession form and lets you review:

- **Collection** – pick the correct collection code.
- **Specimen prefix** – select the locality/prefix that appears on the card.
- **Specimen number** – confirm the interpreted number; it is read-only by
  default but kept with the record for context.
- **Type status** and **Comment** – adjust as required.

Any changes you make are written back into `Media.ocr_data` when you submit the
form, preserving both the previous and the new values in the QC log.

## Managing specimen rows

Each OCR-detected row is rendered with:

- **Specimen suffix** and **Storage area** selectors.
- **Move up / Move down** buttons to reorder rows. The system automatically
  rewrites the row list and sets the `rows_rearranged` flag if the order changes.
- Linked **Identification** fields for taxon, qualifiers, references and
  remarks. Optional fields can be left blank.
- **Specimen details** (element, side, condition, portion, fragments, etc.) for
  each nature entry found on the card. Leave unused fields empty—only populated
  rows are saved back.

Rows without identification or specimen data show guidance text so you know
which sections are empty.

## Submitting for expert review

1. Click **Submit for Expert Review** when you are satisfied with the data.
2. The wizard validates all forms together. If issues are found (e.g. missing
   required choices), errors are displayed inline and nothing is saved yet.
3. On success:
   - Cleaned data replaces the OCR interpretation in `Media.ocr_data`.
   - Field-level diffs are recorded in `MediaQCLog` for audit purposes.
   - The media transitions to the **Pending Expert Review** QC status, stamping
     you as the intern reviewer and preserving the timestamp.
   - You are returned to the dashboard so you can pick up the next task.

If the expert transition raises an error (for example, the data cannot be
forwarded because of a validation rule), the message is surfaced at the top of
the page and you can fix the highlighted fields before retrying.

## Tips

- Changes are transactional—either every update is written together or none at
  all, so you cannot partially save an item.
- When in doubt, leave a note in the **Comment** field so the expert reviewer
  understands why a value was left blank or adjusted.
- The wizard never alters the underlying `Accession` record directly; it only
  prepares the JSON payload and status for expert review.
