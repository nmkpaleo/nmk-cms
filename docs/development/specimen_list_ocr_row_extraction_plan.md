# Specimen List OCR & Row Extraction Plan (Implementation Notes)

## Overview
This document outlines the staging models used to persist raw OCR output and extracted row candidates for specimen list pages. The intent is to preserve reusable OCR output, support re-extraction without repeated OCR calls, and provide an auditable staging area before accession creation.

## Data Staging Models
### SpecimenListPageOCR
- Stores raw OCR output for each specimen list page.
- Captures the OCR engine identifier used for the request.
- Persists bounding box data alongside the raw text for downstream extraction and review.

### SpecimenListRowCandidate
- Stores per-row extraction results for pages classified as specimen list details.
- Tracks the row index, parsed row data (including extra columns as free-form JSON keys), and confidence.
- Supports review workflow statuses (unreviewed, edited, approved, rejected).

## How to Use
1. Run raw OCR for each page and store the verbatim response in the OCR staging table.
2. Run structured row extraction only for pages classified as specimen list details.
3. Review and edit row candidates before downstream accession creation (out of scope for this phase).

## Operational Notes
- Retain raw OCR results to avoid repeated OCR calls and to support reprocessing.
- Treat row candidates as staging data; no accession records are created at this stage.
- Use feature flags or queue controls to roll out extraction in controlled batches.
