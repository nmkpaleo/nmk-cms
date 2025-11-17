# Quality Control

The quality control (QC) workflow moves every scanned card through two review
stages before accessions are created. Interns prepare and tidy the OCR payload,
then experts validate the data, record guidance, and either approve the
accession import or send the record back for more work. Every QC decision is
captured in the audit log alongside optional reviewer comments so both groups
can see the latest guidance inside the wizard itself.

## Workflow overview

1. **Intern review** – interns verify and normalise the OCR results for a media
   card. They correct accession details, reorder rows to match the card layout,
   and ensure specimen information is complete before forwarding the record.
2. **Expert review** – once an intern submits the record, an expert receives the
   refined data, leaves any feedback, and either approves the import or returns
   the card for additional work.

Reviewer comments travel with the QC log. When an expert uses the guidance
textarea, the message is stored with the status change and automatically appears
on the intern wizard the next time the card is opened.

On the dashboard the intern queue is split into two panels:

- **Pending Intern Review** lists new cards as well as items the expert returned
  to interns. A "Return to Interns" action keeps the media in this status.
- **Rejected** lists scans flagged for rescan. Experts move cards here with the
  "Request Rescan" button.

The expert queue shows items waiting for their review and links directly to the
expert QC wizard.

## Intern review wizard

### Accessing the intern QC wizard

- The wizard lives at `/qc/intern/<uuid>/`, where `<uuid>` is the media item's
  public identifier. You can copy this link from the QC queue or the media
  detail view.
- Only users in the **Interns** group can load the page; others receive a
  "403 – Forbidden" response.
- The form is read/write and pre-populates from the existing `Media.ocr_data`
  JSON payload when available.

### Reviewing accession details

The first section mirrors the standard accession form and lets you review:

- **Collection** – pick the correct collection code.
- **Specimen prefix** – select the locality/prefix that appears on the card.
- **Specimen number** – confirm the interpreted number; it stays editable so you
  can fix OCR mistakes.
- **Type status** and **Comment** – adjust as required.

Any changes you make are written back into `Media.ocr_data` when you submit the
form, preserving both the previous and the new values in the QC log.

### Managing specimen rows

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

### Reviewing references

When OCR finds bibliography on the card back, the wizard surfaces each
reference so you can confirm the interpreted author, title, year, and page
range. Update the fields inline if the transcription needs correction—the
cleaned values are saved back to `Media.ocr_data` and inform the expert review
step.

### Checking field slips

Detected field slip information appears in its own section. Verify the field
number, verbatim locality, taxon, and specimen description, along with the
verbatim horizon (formation, member, bed, chronostratigraphy) and any aerial
photo or coordinate data. Adjusting these fields ensures the downstream field
slip linkage is accurate when the media advances to expert review.

### Expert feedback panel

When an expert returns a card to interns, the wizard highlights the latest
comment in a blue callout at the top of the form. Earlier comments remain
available beneath it so you can follow the complete conversation. Review these
notes before resubmitting the record so the expert can see what changed.

### Submitting for expert review

1. Click **Submit for Expert Review** when you are satisfied with the data.
2. The wizard validates all forms together. If issues are found (for example,
   missing required choices), errors are displayed inline and nothing is saved
   yet.
3. On success:
   - Cleaned data replaces the OCR interpretation in `Media.ocr_data`.
   - Field-level diffs are recorded in `MediaQCLog` for audit purposes.
   - The media transitions to the **Pending Expert Review** QC status, stamping
     you as the intern reviewer and preserving the timestamp.
   - You are returned to the dashboard so you can pick up the next task.

If the status transition raises an error (for example, due to a validation
rule), the message is surfaced at the top of the page and you can fix the
highlighted fields before retrying.

## Expert review wizard

### Accessing the expert QC wizard

- Experts can open `/qc/expert/<uuid>/` directly from the dashboard queue.
- Access is limited to superusers, **Curators**, and **Collection Managers**.
- The same form layout appears, prefilled with intern edits so you can inspect
  everything in one place.

### Available actions

- **Save & Continue** – persists any form edits and optional comment while
  keeping the media in its current QC state. Use this to checkpoint work in
  progress.
- **Return to Interns** – sends the record back to the intern queue with the
  **Pending Intern Review** status. Leave a comment so the intern understands
  what needs to change.
- **Request Rescan** – marks the media **Rejected**, which surfaces it in the
  intern "Rejected" dashboard list. Use this when the scan itself is unusable.
- **Approve & Accession** – runs the importer inside a transaction, links the
  resulting accessions back to the media, and marks the record **Approved**. If
  a matching accession already exists you'll be prompted to either create a new
  instance or update the existing record before continuing. The wizard still
  blocks re-approval once the media already owns accessions to avoid duplicates.

### Managing references

Each reference card shows a **Delete reference** button with a trash icon so you
can remove entries that were misinterpreted or are no longer needed. Clicking
the button toggles the formset delete flag for that card and visually marks it
for removal; saving the wizard completes the deletion. Use **Undo delete** to
restore a card before saving if you clicked delete by mistake. The control is
always available on the expert wizard—no feature flag is required.

### Leaving reviewer comments

The expert wizard includes a **Reviewer comment** textarea and a history list of
previous notes. When you submit an action with a comment, it is written to the
QC log and immediately becomes visible to interns in their feedback panel. These
comments persist across subsequent reviews so you can track the discussion.

### Handling importer failures

If the accession importer raises a validation error or exception, the wizard
surfaces the message at the top of the form and keeps the media in the expert
queue. No comment is stored in that case, letting you adjust the data and retry
once the issue is fixed.

### Resolving duplicate accession numbers

When the importer detects that an accession number already exists, the expert
wizard displays a comparison card before approval. Choose **Yes** to create the
next available accession instance automatically, or select **No** to update the
existing record. When updating you can pick which accession fields, specimen
rows, references, and field slips should be replaced with the newly reviewed
values. Once you submit the decision the importer applies your choices, links
the media to the chosen accession, and records the change in the QC history so
the hand-off with interns remains transparent.

## Dashboard queues

- Interns see two quality control tables. Returned items and brand-new scans are
  grouped under **Pending Intern Review**, while rescans flagged by experts live
  in the **Rejected** table.
- Experts see media awaiting their decision under **Pending Expert Review**.
  Every entry links directly to the expert QC wizard for quicker turnaround.

Use the queues together with the shared comment log to keep the hand-off between
interns and experts smooth and well documented.
