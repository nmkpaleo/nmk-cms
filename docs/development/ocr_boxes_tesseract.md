# OCR Token Boxes with Tesseract

## Overview
This project can extract token-level OCR boxes using Tesseract through `pytesseract`.

## Python dependency
Add to application requirements:

- `pytesseract`

## System dependency
Install the Tesseract binary on the host/container:

- Debian/Ubuntu: `apt-get install -y tesseract-ocr`

## Feature flag
Control token-box extraction with:

- `OCR_BOX_TESSERACT_ENABLED=true` (default)
- `OCR_BOX_TESSERACT_ENABLED=false` to disable token-box extraction safely

When disabled, token-box calls should return an empty list without failing the OCR pipeline.

## Optional command override
If Tesseract is installed at a non-default path, set:

- `TESSERACT_CMD=/custom/path/to/tesseract`

## ROI behavior
The backend supports region-of-interest OCR using `(x1, y1, x2, y2)` coordinates.
Returned token coordinates are remapped into full-page coordinates.
