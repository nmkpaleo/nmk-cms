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

## Rollout and rollback
- **Rollout:** Enable the ingestion feature flag in configuration so the upload page is visible to permitted users.
- **Rollback:** Disable the feature flag to hide the upload UI. Existing PDFs and page images remain stored for future processing.
