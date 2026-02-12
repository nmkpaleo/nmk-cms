# Specimen List PDF Ingestion

## Overview
Specimen list PDF ingestion lets staff upload handwritten specimen list PDFs so each page can be split into an image and reviewed independently. Original PDFs are preserved, and the system tracks processing status for each upload.

## User rights
You must be signed in and have the **Add specimen list PDF** permission (`cms.add_specimenlistpdf`) to upload files.

Users without this permission cannot open the upload form.

Related review pages use a separate permission (**Review specimen list page**, `cms.review_specimenlistpage`).

## How to navigate to upload
1. Sign in to CMS.
2. Open the specimen list upload page at:
   - `/specimen-lists/upload/`
3. Use this page to submit one or more PDFs for ingestion.

## Upload requirements
- Use a clear **Source label** to describe the batch (for example: a locality or field season).
- Upload one or more PDFs in a single batch.
- Keep files under the size limits defined by operations.

## What happens after upload
1. The system stores the original PDF with a unique filename.
2. Each PDF is split into page images for review.
3. Page records are created so reviewers can work page by page.

## Next page after upload
After a successful upload, you stay on the same upload page and see a success message confirming how many PDFs were queued.

## Next steps after upload
After upload and queueing, continue with these steps:

1. Open the review queue and find newly created pages.
2. Check OCR and extraction status.
3. Review and approve/reject pages and rows as needed.

Related user guides:
- [Specimen list OCR](specimen_list_ocr.md)
- [Review queue](review_queue.md)
- [Specimen list review](specimen_list_review.md)
- [Specimen list row review](specimen_list_row_review.md)



## Workflow diagram

```text
┌───────────────────────────────┐
│ 1) Upload PDF                 │
│ Page: /specimen-lists/upload/ │
└───────────────┬───────────────┘
                │
                │ Caption: User submits one or more PDFs with Source label.
                ▼
┌──────────────────────────────────────────────────┐
│ 2) Queue Processing                              │
│ PDF status: uploaded                             │
└───────────────┬──────────────────────────────────┘
                │
                │ Caption: Upload is accepted and queued for background split.
                ▼
┌──────────────────────────────────────────────────┐
│ 3) Background Split Worker                       │
│ uploaded -> processing -> split | error          │
└───────────────┬──────────────────────────────────┘
                │
                │ Caption: Worker creates page images from each PDF.
                ▼
┌──────────────────────────────────────────────────┐
│ 4) Page Pipeline                                 │
│ pending -> classified -> ocr_done -> extracted   │
└───────────────┬──────────────────────────────────┘
                │
                │ Caption: Classification, OCR, and row extraction run.
                ▼
┌───────────────────────────────┐
│ 5) Review Queue + Row Review  │
│ review: pending/in_review/... │
└───────────────┬───────────────┘
                │
                │ Caption: Reviewer validates, edits, approves, or rejects.
                ▼
┌───────────────────────────────┐
│ 6) Approval + Persistence     │
│ page: approved/rejected       │
└───────────────────────────────┘
Caption: Approved rows create/update accession data.
```

## Status transitions and triggers

### PDF status (`SpecimenListPDF.status`)
- `uploaded`: set immediately after upload; queued for split.
- `processing`: set when background/manual split starts.
- `split`: set when page images are successfully created.
- `error`: set when split fails (missing file/path or split command failure).

### Page pipeline status (`SpecimenListPage.pipeline_status`)
- `pending`: initial page state after split.
- `classified`: set after successful page-type classification.
- `ocr_done`: set after raw OCR completes.
- `extracted`: set after row extraction completes.
- `in_review`: set when review lock/assignment starts.
- `approved` / `rejected`: set by reviewer decisions.

### Page review status (`SpecimenListPage.review_status`)
- `pending`: ready for review assignment.
- `in_review`: actively locked by a reviewer.
- `approved` / `rejected`: final review outcome.

## Async/background processing and manual processing
- Upload enqueues processing; split can run in the background.
- If your deployment runs queues manually, admins can trigger stages with:
  - `python app/manage.py process_specimen_list_pdfs`
  - `python app/manage.py process_specimen_list_ocr --stage raw`
  - `python app/manage.py process_specimen_list_ocr --stage rows`

## Re-run after errors
- If a PDF is in `error`, an admin can re-run split processing.
- OCR and row extraction can be re-run on failed/incomplete pages using the OCR command with `--stage` and optional `--force`.
- Review can proceed once page status reaches `extracted` and rows are available.

## Rollout and rollback
- **Rollout:** Enable the ingestion feature flag in configuration so the upload page is visible to permitted users.
- **Rollback:** Disable the feature flag to hide the upload UI. Existing PDFs and page images remain stored for future processing.

## QC evidence during review
When reviewing extracted rows, the table includes read-only QC evidence columns:

- **Element (raw OCR)**
- **Element (corrected)**
- **Tooth-marking detections**

Use these to verify why a replacement was applied before approving the page.
