# Scan Uploads (User)

Collection Managers can submit scanned images for processing.

## Uploading Scans
1. Sign in to the Django admin site.
2. Click **Upload scans** in the header.
3. Choose one or more files using a supported name:
   - `YYYY-MM-DDTHHMMSS.png`, for example `2026-09-16T143025.png`, for OCR processing.
   - Digits, two letters, one space, and digits followed by `.png`, for example `4LT 1082726110849.png`, for OCR processing without a scanning-session link. Letters and extensions are case-insensitive.
   - Digits followed by `.jpg` or `.jpeg`, for example `00123.jpg`, for manual quality control.
4. Submit the form to validate the files and queue them for processing.

The system moves valid OCR files to the pending folder and manual QC files to the manual QC folder, creating matching Media records. See [Scan Uploads (Admin)](../admin/scan-uploads.md) for details.
