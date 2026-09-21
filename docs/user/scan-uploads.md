# Scan Uploads (User)

Collection Managers can submit scanned images for processing.

## Uploading Scans
1. Sign in to the Django admin site.
2. Click **Upload scans** in the header.
3. Choose one or more files using a supported name:
   - `YYYY-MM-DDTHHMMSS.png`, for example `2026-09-16T143025.png`, for OCR processing.
   - `YYMMDDHHMMSSN.png`, for example `2609211113551.png` or `2609211113553.png`, for OCR processing. The first 12 digits give the Nairobi scan time (years 2000-2099); `N` is one or more digits. The timestamp is used to find the scanning session. The PNG extension is case-insensitive.
   - Digits, two letters, one space, and digits followed by `.png`, for example `4LT 1082726110849.png`, for OCR processing without a scanning-session link. Letters and extensions are case-insensitive.
   - Digits followed by `.jpg` or `.jpeg`, for example `00123.jpg`, for manual quality control.
4. Submit the form to validate the files and queue them for processing.

The system moves valid OCR files to the pending folder and manual QC files to the manual QC folder, creating matching Media records. See [Scan Uploads (Admin)](../admin/scan-uploads.md) for details.

## Duplicate filenames

Uploading a filename already recorded in Media or present in an uploads folder skips that file without replacing it or creating another Media record. The message identifies the existing folder and batch position, for example: `Already uploaded 9LT 1082726110849.png into uploads/ocr folder (7 of 7)`. Other new files in the batch continue uploading.
