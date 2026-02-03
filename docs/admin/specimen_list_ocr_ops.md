# Specimen List OCR Operations

## Overview
This guide covers the Stage A raw OCR workflow for specimen list pages. Raw OCR results are stored verbatim so that row extraction can be rerun without repeating OCR requests.

## Running Raw OCR
1. Ensure specimen list pages have images available.
2. Run the raw OCR queue for the pages you want to process.
3. Verify that each page now has a raw OCR entry before moving to row extraction.

## Queue Commands
- Run both raw OCR and row extraction:
  - `python app/manage.py process_specimen_list_ocr`
- Run only raw OCR:
  - `python app/manage.py process_specimen_list_ocr --stage raw`
- Run only row extraction:
  - `python app/manage.py process_specimen_list_ocr --stage rows`

Use `--limit` to cap batch sizes or configure defaults via the batch size settings.

## Reprocessing Guidance
- Raw OCR results are retained for auditability.
- Re-run OCR only when needed (for example, after image cleanup).
- Avoid overwriting prior OCR entries unless you are explicitly reprocessing.

## Pipeline Status Notes
- Raw OCR completion updates pages to the OCR done pipeline status.
- Row extraction completion updates pages to the extracted pipeline status for detail pages.

## Failure Handling
- Failed OCR attempts are logged with error details.
- Retry failed pages after resolving API or network issues.
