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

## Related guides
- [Specimen list OCR operations](specimen_list_ocr_ops.md)
- [Approval workflow](approval_workflow.md)
- [User ingestion walkthrough](../user/specimen_list_ingestion.md)
- [User review queue](../user/review_queue.md)
