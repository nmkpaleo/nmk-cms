# Scan Uploads (Admin)

Staff can upload scanned images directly into the CMS for further processing.

## Uploading Scans
1. Log in to the Django admin site.
2. Use the **Upload scans** button in the header.
3. Select one or more files that follow one of the supported naming formats:
   - `YYYY-MM-DDTHHMMSS.png` for standard OCR scans (moved to `uploads/pending/`).
   - Digits, two letters, one space, and digits followed by `.png`, for example `4LT 1082726110849.png`. These enter `uploads/pending/` for OCR without a scanning-session link because they have no filename timestamp. Letters and extensions are case-insensitive.
   - `NNN.jpg` (only digits before the extension) for manual QC scans (moved to `uploads/manual_qc/`).
4. Click **Upload**. Each file is validated and moved to the appropriate folder.

## After Upload
- Valid OCR files are moved to `uploads/pending/` and create a corresponding Media entry.
- Manual QC JPEGs are moved to `uploads/manual_qc/` and immediately create a Media entry ready for the manual import workflow.
- Files with other naming patterns are moved to `uploads/rejected/` for manual review.

## Duplicate filenames

Uploading a filename already recorded in Media or present in an uploads folder skips that file without replacing it or creating another Media record. The message identifies the existing folder and batch position, for example: `Already uploaded 9LT 1082726110849.png into uploads/ocr folder (7 of 7)`. Other new files in the batch continue uploading.

Web uploads are staged in a private temporary directory under the media root, then processed by the web request. The incoming-folder watcher remains responsible for files delivered directly to `uploads/incoming/`. Web batches and the watcher share `.scan-upload.lock` under the media root; workers must share this filesystem and support file locking. The existing-file index is built once per web batch.
