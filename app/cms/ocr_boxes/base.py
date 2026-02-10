from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeAlias

from PIL import Image


ImageInput: TypeAlias = Image.Image | Path | str
ROI: TypeAlias = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class TokenBox:
    """Represents a token-level OCR bounding box on a page image."""

    token_id: int
    text: str
    conf: float | None
    x1: int
    y1: int
    x2: int
    y2: int
    line_id: int | None = None
    block_id: int | None = None


class OCRBoxBackend(Protocol):
    """Protocol implemented by OCR backends that provide token boxes."""

    def get_token_boxes(
        self,
        image: ImageInput,
        *,
        roi: ROI | None = None,
    ) -> list[TokenBox]:
        """Return token boxes for ``image`` and optional ROI."""

