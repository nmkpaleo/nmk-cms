# Tooth-marking inference vendor package

This package vendor-copies the inference-only flow from:
`korolainenriikka/fine-tuned-ocr-for-dental-markings/pretrained_models/demo.ipynb`.

## Ported notebook cells

- **Cell 1 (imports + seed):** runtime imports ported (`torch`, `torchvision.transforms`, `PIL`).
- **Cell 2 (model loading):** four pretrained models loaded from `.pt` files.
- **Cell 3 (class mappings):** label maps for `upperlower`, `mpi`, `123`, `1234`.
- **Cell 4 (preprocess):** `Grayscale(3) -> Resize(224,224) -> ToTensor -> Normalize([0.5]*3, [0.2]*3)`.
- **Cell 5 (inference helpers):** batched inference, no-grad inference mode, prediction mapping.
- **Cell 7 (classifier chain):** jaw + type + index, where index model depends on predicted type (`P` uses `1234`, otherwise `123`).
- **Cell 7 (postprocess notation):** output notation uses uppercase for upper jaw and lowercase for lower jaw (e.g., `M2`, `m2`).

## Runtime assets

Expected model files (default path: `cms/tooth_markings/assets/`):

- `upperlower.pt`
- `MPI.pt`
- `123.pt`
- `1234.pt`

These model binaries are **not committed** to this repo to keep the PR free of binary assets.
Download them using instructions in `assets/README.md`, or set `TOOTH_MARKINGS_MODEL_DIR`
to an external directory containing the files.

## Public API

```python
from cms.tooth_markings.service import correct_element_text

result = correct_element_text("Element m2")
# token_crops omitted: no inference yet, returns unchanged text + empty detections
```

With token crops:

```python
result = correct_element_text(
    "Element m2",
    token_crops=[
        {"token": "m2", "image": pil_or_path, "start": 8, "end": 10},
    ],
)
```
