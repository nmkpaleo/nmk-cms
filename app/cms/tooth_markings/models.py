"""Model loading for tooth-marking inference-only classifiers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import torch

_ASSET_ENV = "TOOTH_MARKINGS_MODEL_DIR"
_DEFAULT_ASSET_DIR = Path(__file__).resolve().parent / "assets"


@dataclass(frozen=True)
class ModelBundle:
    uplow_model: torch.nn.Module
    mpi_model: torch.nn.Module
    index_model_123: torch.nn.Module
    index_model_1234: torch.nn.Module
    device: torch.device


def _resolve_asset_path(filename: str) -> Path:
    model_dir = Path(os.environ.get(_ASSET_ENV, _DEFAULT_ASSET_DIR))
    path = model_dir / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Missing model file: {path}. Set {_ASSET_ENV} to a directory with .pt model files."
        )
    return path


def _validate_not_lfs_pointer(path: Path) -> None:
    """Raise a clear error when model files are Git LFS pointer placeholders."""
    with path.open("rb") as fh:
        header = fh.read(200)
    if b"git-lfs.github.com/spec/v1" in header:
        raise RuntimeError(
            "Model file appears to be a Git LFS pointer, not real weights: "
            f"{path}. See assets/README.md for download instructions."
        )


def _load_model(path: Path, device: torch.device) -> torch.nn.Module:
    _validate_not_lfs_pointer(path)

    # Torch 2.6+ changed default torch.load behavior toward ``weights_only=True``.
    # Our packaged .pt assets may contain full serialized modules, so we force
    # ``weights_only=False`` when supported and gracefully fall back for older
    # torch versions that do not expose this keyword argument.
    try:
        model = torch.load(path, map_location=device, weights_only=False)
    except TypeError:
        model = torch.load(path, map_location=device)

    model = model.to(device)
    model.eval()
    return model


@lru_cache(maxsize=1)
def get_models() -> ModelBundle:
    """Load and cache all inference models once per process."""
    device = torch.device("cpu")
    return ModelBundle(
        uplow_model=_load_model(_resolve_asset_path("upperlower.pt"), device),
        mpi_model=_load_model(_resolve_asset_path("MPI.pt"), device),
        index_model_123=_load_model(_resolve_asset_path("123.pt"), device),
        index_model_1234=_load_model(_resolve_asset_path("1234.pt"), device),
        device=device,
    )
