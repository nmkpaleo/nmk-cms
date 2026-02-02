# Specimen List PDF Ingestion (Admin)

## Overview
Admins can monitor specimen list PDF ingestion in Django admin, review processing status, and requeue failed PDFs for another splitting attempt.

## Admin workflow
1. Open **Specimen list PDFs** in the admin.
2. Review the status, page count, and uploader details.
3. If a PDF is marked as **Error**, use **Requeue splitting** to retry the page-splitting pipeline.

## Operational notes
- Requeueing is available only for PDFs in an error state.
- Page records are recreated during reprocessing to keep the page list consistent with the source PDF.
- Ensure the offline processing command is scheduled so queued PDFs are split into pages.

## Rollout and rollback
- **Rollout:** Enable the ingestion feature flag in configuration to expose the upload and review UI to staff.
- **Rollback:** Disable the feature flag to hide the ingestion UI. Existing uploads remain stored for later reprocessing.
