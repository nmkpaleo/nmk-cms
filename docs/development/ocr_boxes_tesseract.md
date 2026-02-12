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

## Manual debug command
Use the debug command when validating tooth-marking correction on a single page image.

```bash
cd app
python manage.py tooth_marking_debug \
  --image /path/to/page.png \
  --text "Ml" \
  --roi 100,200,500,650 \
  --overlay-out /tmp/tooth_marking_overlay.png
```

What it does:

- Prints raw element text, corrected element text, and number of replacements applied.
- Prints a detection summary (`token_raw`, notation, confidence, span).
- Optionally saves a debug overlay image with token boxes highlighted.

Tips:

- Omit `--roi` to run on the full page.
- Use `--min-confidence 0.90` to test stricter replacement thresholds during manual verification.

## Feature flags, dependencies, and fallback behavior
- `OCR_BOX_TESSERACT_ENABLED` controls token-box extraction (`true` by default).
- `OCR_BOX_ENGINE` can select optional engines; non-configured/missing engines fail safe and return empty token boxes.
- `TOOTH_MARKING_MIN_CONF` controls replacement confidence threshold in the integration helper.

Fallback behavior is defensive:

- Missing Tesseract binary/import errors: token-box calls return empty lists with warning logs.
- Tooth-marking correction exceptions: the helper preserves raw text, returns deterministic keys, and sets `error` in payload.
