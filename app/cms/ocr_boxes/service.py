from __future__ import annotations

from pathlib import Path

from PIL import Image

from .base import ImageInput, OCRBoxBackend, ROI, TokenBox


class NullOCRBoxBackend:
    """Fallback backend used until a concrete OCR engine is configured."""

    def get_token_boxes(
        self,
        image: ImageInput,
        *,
        roi: ROI | None = None,
    ) -> list[TokenBox]:
        return []


_backend: OCRBoxBackend = NullOCRBoxBackend()


def configure_backend(backend: OCRBoxBackend) -> None:
    """Set the backend used by :func:`get_token_boxes`."""

    global _backend
    _backend = backend


def get_token_boxes(image: ImageInput, roi: ROI | None = None) -> list[TokenBox]:
    """Return token boxes from the configured OCR backend."""

    return _backend.get_token_boxes(image, roi=roi)


def _as_pil_image(image: ImageInput) -> Image.Image:
    if isinstance(image, Image.Image):
        return image
    with Image.open(Path(image)) as opened:
        return opened.copy()


def get_token_crops(
    image: ImageInput,
    token_boxes: list[TokenBox],
) -> list[dict[str, object]]:
    """Return per-token crops and metadata from ``token_boxes``."""

    source = _as_pil_image(image)
    width, height = source.size
    crops: list[dict[str, object]] = []

    for box in token_boxes:
        x1 = max(0, min(box.x1, width))
        y1 = max(0, min(box.y1, height))
        x2 = max(x1, min(box.x2, width))
        y2 = max(y1, min(box.y2, height))

        crops.append(
            {
                "token": box.text,
                "bbox": (x1, y1, x2, y2),
                "image": source.crop((x1, y1, x2, y2)),
                "conf": box.conf,
            }
        )

    return crops

