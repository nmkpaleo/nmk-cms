# Specimen List OCR Operations

## Overview
This guide covers the Stage A raw OCR workflow for specimen list pages. Raw OCR results are stored verbatim so that row extraction can be rerun without repeating OCR requests.

## Running Raw OCR
1. Ensure specimen list pages have images available.
2. Run the raw OCR task for the pages you want to process.
3. Verify that each page now has a raw OCR entry before moving to row extraction.

## Reprocessing Guidance
- Raw OCR results are retained for auditability.
- Re-run OCR only when needed (for example, after image cleanup).
- Avoid overwriting prior OCR entries unless you are explicitly reprocessing.

## Failure Handling
- Failed OCR attempts are logged with error details.
- Retry failed pages after resolving API or network issues.
