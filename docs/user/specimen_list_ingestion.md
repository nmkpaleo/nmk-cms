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
┌───────────────────────────────┐
│ 2) Queue + Store Original PDF │
└───────────────┬───────────────┘
                │
                │ Caption: System saves originals and starts background processing.
                ▼
┌───────────────────────────────┐
│ 3) Split PDF into Page Images │
└───────────────┬───────────────┘
                │
                │ Caption: One record per page is created.
                ▼
┌───────────────────────────────┐
│ 4) OCR + Row Extraction       │
└───────────────┬───────────────┘
                │
                │ Caption: OCR text and row candidates are prepared for review.
                ▼
┌───────────────────────────────┐
│ 5) Review Queue + Row Review  │
└───────────────┬───────────────┘
                │
                │ Caption: Reviewer validates, edits, approves, or rejects.
                ▼
┌───────────────────────────────┐
│ 6) Approval + Persistence     │
└───────────────────────────────┘
Caption: Approved rows create/update accession data.
```

## Rollout and rollback
- **Rollout:** Enable the ingestion feature flag in configuration so the upload page is visible to permitted users.
- **Rollback:** Disable the feature flag to hide the upload UI. Existing PDFs and page images remain stored for future processing.
