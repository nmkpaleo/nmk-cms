# Scan Uploads (Admin)

Staff can upload scanned images directly into the CMS for further processing.

## Uploading Scans
1. Log in to the Django admin site.
2. Use the **Upload scans** button in the header.
3. Select one or more files that follow the `YYYY-MM-DD(n).png` naming format.
4. Click **Upload**. Each file is validated and moved to the appropriate folder.

## After Upload
- Valid files are moved to `uploads/pending/` and create a corresponding Media entry.
- Files with invalid names are moved to `uploads/rejected/` for manual review.
