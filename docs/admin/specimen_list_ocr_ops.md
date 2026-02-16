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

## Feature Flags
- `SPECIMEN_LIST_ROW_EXTRACTION_ENABLED` controls whether row extraction runs.
- Batch size defaults can be set with `SPECIMEN_LIST_OCR_BATCH_SIZE` and `SPECIMEN_LIST_ROW_EXTRACTION_BATCH_SIZE`.

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

## Rollback Steps
1. Disable row extraction by setting `SPECIMEN_LIST_ROW_EXTRACTION_ENABLED` to false.
2. Pause queue runs for row extraction while keeping raw OCR available for later reprocessing.


## Tooth-marking dependency rollout checklist

When enabling or updating the optional tooth-marking CPU inference stack:

1. Confirm the environment can install from `app/requirements-tooth-marking-cpu.txt`.
2. Run the tooth-marking debug command with a known sample image and confirm corrected output is reasonable.
3. Validate that row review still saves corrected element text and detection evidence.
4. Spot-check Nature of Specimen records in admin to ensure detection JSON is readable.

## Tooth-marking rollback checklist

If a dependency update causes regressions:

1. Restore the last known-good optional CPU dependency pins.
2. Rebuild/redeploy the application environment.
3. Re-run a small OCR/review sample and confirm corrections and detections are stable.
4. Keep review queues active; historical detection data remains intact.
