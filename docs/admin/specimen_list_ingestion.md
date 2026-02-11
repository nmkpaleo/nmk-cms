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
│ B) PDF queued and original file persisted  │
└───────────────────┬────────────────────────┘
                    │
                    │ Caption: Processing can be async or command-driven.
                    ▼
┌────────────────────────────────────────────┐
│ C) PDF split into page images              │
└───────────────────┬────────────────────────┘
                    │
                    │ Caption: Page objects are created for downstream stages.
                    ▼
┌────────────────────────────────────────────┐
│ D) OCR stages + row extraction             │
└───────────────────┬────────────────────────┘
                    │
                    │ Caption: Operations monitor OCR queues and retries.
                    ▼
┌────────────────────────────────────────────┐
│ E) Review queues + approvals               │
└───────────────────┬────────────────────────┘
                    │
                    │ Caption: Requires cms.review_specimenlistpage.
                    ▼
┌────────────────────────────────────────────┐
│ F) Approved data persisted + image moved   │
└────────────────────────────────────────────┘
Caption: Audit trail and status updates are retained.
```

## Related guides
- [Specimen list OCR operations](specimen_list_ocr_ops.md)
- [Approval workflow](approval_workflow.md)
- [User ingestion walkthrough](../user/specimen_list_ingestion.md)
- [User review queue](../user/review_queue.md)
