"""Per-head prediction helpers for tooth-marking models."""

from __future__ import annotations

from typing import Dict, Tuple

import torch
from torch import Tensor

from .models import get_models

CLASS_TO_IDX: Dict[str, Dict[str, int]] = {
    "123": {"1": 0, "2": 1, "3": 2},
    "mpi": {"I": 0, "M": 1, "P": 2},
    "1234": {"1": 0, "2": 1, "3": 2, "4": 3},
    "upperlower": {"low": 0, "up": 1},
}


def _idx_to_class(head: str, index: int) -> str:
    for label, idx in CLASS_TO_IDX[head].items():
        if idx == index:
            return label
    raise KeyError(f"No label mapping for head={head} index={index}")


def _infer(model: torch.nn.Module, input_batch: Tensor) -> Tuple[int, float]:
    with torch.inference_mode():
        logits = model(input_batch)

        # Keep compatibility with model wrappers that return a tuple/list
        # (e.g., (logits, aux)) rather than a bare tensor.
        if isinstance(logits, (tuple, list)):
            logits = logits[0]

        probs = torch.softmax(logits, dim=1)
        best_prob, best_idx = torch.max(probs, dim=1)
        return int(best_idx.item()), float(best_prob.item())


def predict_jaw(input_batch: Tensor) -> Tuple[str, float]:
    """Predict 'up' or 'low' jaw class and probability."""
    idx, prob = _infer(get_models().uplow_model, input_batch)
    return _idx_to_class("upperlower", idx), prob


def predict_type(input_batch: Tensor) -> Tuple[str, float]:
    """Predict tooth type class ('I', 'M', 'P') and probability."""
    idx, prob = _infer(get_models().mpi_model, input_batch)
    return _idx_to_class("mpi", idx), prob


def predict_index(input_batch: Tensor, *, type_label: str) -> Tuple[str, float]:
    """Predict tooth index class.

    Uses 1234 model for premolars (P), else 123 model.
    """
    models = get_models()
    model = models.index_model_1234 if type_label == "P" else models.index_model_123
    head = "1234" if type_label == "P" else "123"
    idx, prob = _infer(model, input_batch)
    return _idx_to_class(head, idx), prob
