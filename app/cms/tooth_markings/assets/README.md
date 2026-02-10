# Tooth-marking pretrained assets

This folder is the default runtime location for assets referenced by Riikka Korolainen's
`pretrained_models/demo.ipynb`:

- `upperlower.pt`
- `MPI.pt`
- `123.pt`
- `1234.pt`

> Note: model binaries are not committed in this repository. Download the real weights from
> GitHub media endpoints and place them here, or point `TOOTH_MARKINGS_MODEL_DIR` to a
> directory that contains the real model files.

Example download commands:

```bash
curl -L -o upperlower.pt https://media.githubusercontent.com/media/korolainenriikka/fine-tuned-ocr-for-dental-markings/main/pretrained_models/upperlower.pt
curl -L -o MPI.pt https://media.githubusercontent.com/media/korolainenriikka/fine-tuned-ocr-for-dental-markings/main/pretrained_models/MPI.pt
curl -L -o 123.pt https://media.githubusercontent.com/media/korolainenriikka/fine-tuned-ocr-for-dental-markings/main/pretrained_models/123.pt
curl -L -o 1234.pt https://media.githubusercontent.com/media/korolainenriikka/fine-tuned-ocr-for-dental-markings/main/pretrained_models/1234.pt
```
