# Specimen List OCR

## Overview
Specimen list OCR runs in two stages:
1. **Raw OCR** stores verbatim text and bounding boxes for each page.
2. **Row extraction** parses rows for specimen list detail pages so reviewers can approve or reject candidates.

## How to Run OCR
1. Upload a specimen list PDF and allow the pipeline to split it into pages.
2. Run the OCR queue to populate raw OCR data.
3. Run row extraction for detail pages and proceed to row review.

## What You Will See
- Raw OCR is stored for each page, even if it is free text.
- Row candidates appear only for pages classified as specimen list details.
- Reviewers can edit, approve, or reject extracted rows.

## Rollback Guidance
If row extraction needs to be paused, an administrator can disable it via the feature flag. Raw OCR remains available for later reprocessing.


## Tooth-marking assistance availability

For element text corrections, the system may apply optional tooth-marking assistance when that runtime is enabled.

- If assistance is active, reviewers may see corrected element text and detection evidence in review workflows.
- If assistance is unavailable or temporarily disabled, review still works and preserves the original OCR text.
- You can continue approving rows while operations teams validate or roll back optional dependency updates.
