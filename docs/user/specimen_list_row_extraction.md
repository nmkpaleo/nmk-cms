# Specimen List Row Extraction

## Overview
Row extraction is the second stage of the specimen list OCR pipeline. It uses the raw OCR text and the page image to detect tabular rows and capture structured values for review.

## When Extraction Runs
- Extraction only runs on pages classified as specimen list details.
- Raw OCR must exist before row extraction can be performed.

## What Gets Stored
Each extracted row is stored as a row candidate with:
- The parsed fields (including any extra columns captured as free-form keys).
- A per-row confidence value when provided.
- A review status so that editors can approve or reject before accession creation.

## Handling Ditto Marks
Ditto marks (e.g., ″, ”, 〃, "11", "!!") indicate a value should repeat from the row above. Extraction expands these marks automatically so rows keep complete values.

## Review Guidance
Review row candidates for accuracy before proceeding with downstream accession creation. Re-run extraction if the raw OCR was updated.
