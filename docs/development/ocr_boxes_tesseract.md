# OCR Token Boxes with Tesseract

## Overview
This project extracts token-level OCR boxes with Tesseract through `pytesseract`.

Tesseract is CPU-friendly and is the recommended production path for OCR boxes.

## Python dependency
Included in base application requirements:

- `pytesseract`

## System dependency
Install the Tesseract binary on the host/container:

- Debian/Ubuntu: `apt-get install -y tesseract-ocr`

## Feature flag
Control token-box extraction with:

- `OCR_BOX_TESSERACT_ENABLED=true` (default)
- `OCR_BOX_TESSERACT_ENABLED=false` to disable token-box extraction safely

When disabled, token-box calls return an empty list without failing the OCR pipeline.

## Optional command override
If Tesseract is installed at a non-default path, set:

- `TESSERACT_CMD=/custom/path/to/tesseract`

## ROI behavior
The backend supports region-of-interest OCR using `(x1, y1, x2, y2)` coordinates.
Returned token coordinates are remapped into full-page coordinates.

## Lean production requirements split
Base production install is intentionally lean and does not include heavyweight ML wheels.

- Use `app/requirements.txt` for standard deployment.
- Install optional tooth-marking CPU inference stack only when needed:
  - `pip install -r app/requirements-tooth-marking-cpu.txt`

This avoids pulling CUDA/GPU wheels in default production installs.
