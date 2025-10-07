"""Helpers for fuzzy string matching used during merge candidate discovery."""
from __future__ import annotations

from typing import Iterable, Tuple

try:  # pragma: no cover - dependency injection is environment specific
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    try:
        from fuzzywuzzy import fuzz  # type: ignore[assignment]
    except ImportError:  # pragma: no cover
        fuzz = None  # type: ignore[assignment]


def similarity_ratio(left: str, right: str) -> float:
    """Return the token set similarity ratio between two strings."""

    if not fuzz:
        raise RuntimeError("Fuzzy matching dependencies are not installed.")
    return float(fuzz.token_set_ratio(left or "", right or ""))


def rank_candidates(source: str, candidates: Iterable[str]) -> Tuple[str, float]:
    """Return the best matching candidate using the configured fuzzy scorer."""

    best_value: float = -1
    best_candidate: str = ""
    for candidate in candidates:
        score = similarity_ratio(source, candidate)
        if score > best_value:
            best_value = score
            best_candidate = candidate
    return best_candidate, best_value
