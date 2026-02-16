# Scan Uploads (Admin)

Staff can upload scanned images directly into the CMS for further processing.

## Uploading Scans
1. Log in to the Django admin site.
2. Use the **Upload scans** button in the header.
3. Select one or more files that follow one of the supported naming formats:
   - `YYYY-MM-DDTHHMMSS.png` for standard OCR scans (moved to `uploads/pending/`).
   - `NNN.jpg` (only digits before the extension) for manual QC scans (moved to `uploads/manual_qc/`).
4. Click **Upload**. Each file is validated and moved to the appropriate folder.

## After Upload
- Valid OCR files are moved to `uploads/pending/` and create a corresponding Media entry.
- Manual QC JPEGs are moved to `uploads/manual_qc/` and immediately create a Media entry ready for the manual import workflow.
- Files with other naming patterns are moved to `uploads/rejected/` for manual review.
