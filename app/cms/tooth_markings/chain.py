"""Classifier-chain inference for full tooth notation."""

from __future__ import annotations

from typing import Dict, Tuple

from PIL import Image

from .predict import predict_index, predict_jaw, predict_type
from .preprocess import image_to_batch


def classify_token_image(image: Image.Image) -> Tuple[str, float, Dict[str, Dict[str, float | str]]]:
    """Predict tooth notation from one token crop image.

    Returns:
        notation: e.g. 'M2' or 'm2' (notebook format)
        confidence: min probability across chain
        parts: structured jaw/type/index predictions
    """
    image_rgb = image.convert("RGB")
    input_batch = image_to_batch(image_rgb)

    jaw_label, jaw_prob = predict_jaw(input_batch)
    type_label, type_prob = predict_type(input_batch)
    index_label, index_prob = predict_index(input_batch, type_label=type_label)

    letter = type_label.upper() if jaw_label == "up" else type_label.lower()
    notation = f"{letter}{index_label}"
    confidence = min(jaw_prob, type_prob, index_prob)

    parts: Dict[str, Dict[str, float | str]] = {
        "jaw": {"label": jaw_label, "prob": jaw_prob},
        "type": {"label": type_label, "prob": type_prob},
        "index": {"label": index_label, "prob": index_prob},
    }
    return notation, confidence, parts
