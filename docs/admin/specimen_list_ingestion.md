# Specimen List Ingestion (Admin)

## Access rights
Users need upload permission to add specimen list PDFs:

- `cms.add_specimenlistpdf`

For downstream review and approval work, users also need:

- `cms.review_specimenlistpage`

## Where upload happens
Use the specimen list upload form:

- `/specimen-lists/upload/`

## What to do after upload
After upload, PDFs are queued for split/processing. The next admin steps are:

1. Confirm pages were created and classified through the queue views.
2. Run OCR pipeline stages if your environment uses manual queue processing.
3. Open review queues and assign/approve work.



## Workflow diagram

```text
┌────────────────────────────────────────────┐
│ A) Admin/User uploads PDF batch            │
│ Route: /specimen-lists/upload/             │
└───────────────────┬────────────────────────┘
                    │
                    │ Caption: Requires cms.add_specimenlistpdf.
                    ▼
┌────────────────────────────────────────────┐
│ B) Queue + Initial status                  │
│ PDF status: uploaded                       │
└───────────────────┬────────────────────────┘
                    │
                    │ Caption: Processing is queued (async/background-friendly).
                    ▼
┌────────────────────────────────────────────┐
│ C) Split worker                            │
│ uploaded -> processing -> split | error    │
└───────────────────┬────────────────────────┘
                    │
                    │ Caption: PDF pages become image records.
                    ▼
┌────────────────────────────────────────────┐
│ D) Page pipeline worker stages             │
│ pending -> classified -> ocr_done -> extracted │
└───────────────────┬────────────────────────┘
                    │
                    │ Caption: Classification + raw OCR + row extraction.
                    ▼
┌────────────────────────────────────────────┐
│ E) Review + approval                       │
│ review_status: pending/in_review/...       │
│ pipeline_status: in_review/approved/rejected│
└───────────────────┬────────────────────────┘
                    │
                    │ Caption: Requires cms.review_specimenlistpage.
                    ▼
┌────────────────────────────────────────────┐
│ F) Persisted outcomes                      │
│ accession rows / field slips / media links │
└────────────────────────────────────────────┘
Caption: Approval writes curated data and audit metadata.
```

## Status codes and trigger events

### PDF status (`SpecimenListPDF.status`)
- `uploaded`: set on upload creation.
- `processing`: set when `process_specimen_list_pdf` starts.
- `split`: set when all pages are split and saved.
- `error`: set on missing file/path or split failure.

### Page status (`SpecimenListPage.pipeline_status`)
- `pending`: created page, no stage completed yet.
- `classified`: set by classification queue.
- `ocr_done`: set by raw OCR queue.
- `extracted`: set by row extraction queue.
- `in_review`: set when page is actively reviewed.
- `approved` / `rejected`: set by review outcomes.

### Review status (`SpecimenListPage.review_status`)
- `pending`: unclaimed.
- `in_review`: claimed/locked.
- `approved` / `rejected`: completed review state.

## Async/background behavior
- Upload always queues processing.
- Split can run asynchronously (deployment setting) or manually through management commands.
- OCR and extraction stages run in queue batches and can be targeted by page IDs.

## Re-run and error recovery
1. **PDF split errors** (`status=error`):
   - Re-run: `python app/manage.py process_specimen_list_pdfs --ids <pdf_id>`
2. **OCR stage issues**:
   - Raw OCR: `python app/manage.py process_specimen_list_ocr --stage raw --ids <page_id>`
   - Row extraction: `python app/manage.py process_specimen_list_ocr --stage rows --ids <page_id>`
3. **Force refresh existing results**:
   - Add `--force` to re-run OCR/extraction despite existing outputs.

## Related guides
- [Specimen list OCR operations](specimen_list_ocr_ops.md)
- [Approval workflow](approval_workflow.md)
- [User ingestion walkthrough](../user/specimen_list_ingestion.md)
- [User review queue](../user/review_queue.md)

## QC surfacing for tooth-marking corrections
On the page review table, reviewers can inspect correction evidence directly in dedicated columns:

- **Element (raw OCR)**: the pre-correction element text.
- **Element (corrected)**: confidence-filtered corrected value used for persistence/QC.
- **Tooth-marking detections**: detection payload used to produce replacements.

In Django admin, `NatureOfSpecimen` records expose:

- `verbatim_element` (corrected value),
- `verbatim_element_raw` (original OCR value),
- tooth-marking detection count and full detection JSON for audit checks.
