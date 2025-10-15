"""Helpers for fuzzy string matching used during merge candidate discovery."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from django.db import models

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


@dataclass(frozen=True)
class CandidateMatch:
    """Representation of a single merge candidate score."""

    instance: models.Model
    score: float
    combined_text: str


def _yield_candidate_text(instance: models.Model, fields: Sequence[str]) -> str:
    """Return a normalised string representation for ``instance`` fields."""

    parts: List[str] = []
    for field_name in fields:
        value = getattr(instance, field_name, "")
        if value in (None, ""):
            continue
        parts.append(str(value))
    return " ".join(parts)


def score_candidates(
    model: type[models.Model],
    query: str,
    *,
    fields: Sequence[str],
    threshold: float = 0,
    queryset: models.QuerySet | None = None,
) -> List[CandidateMatch]:
    """Return an ordered list of candidate matches for ``query``.

    Parameters
    ----------
    model:
        Django model class that should be evaluated.
    query:
        Search phrase supplied by the admin user.
    fields:
        Iterable of field names that should be concatenated to build the text
        corpus for each record.
    threshold:
        Minimum fuzzy ratio (0-100) a candidate must score to be included in
        the result set. The default of ``0`` effectively disables thresholding.
    queryset:
        Optional queryset limiting the records evaluated. When omitted the
        model's default manager will be used.

    Returns
    -------
    list[CandidateMatch]
        Ordered list of matches sorted by score in descending order.
    """

    if not query:
        return []

    if queryset is None:
        queryset = model._default_manager.all()

    cleaned_fields: List[str] = [field for field in fields if field]
    if not cleaned_fields:
        return []

    matches: List[CandidateMatch] = []
    for instance in queryset.iterator():
        combined_text = _yield_candidate_text(instance, cleaned_fields)
        if not combined_text:
            continue
        score = similarity_ratio(query, combined_text)
        if score < threshold:
            continue
        matches.append(CandidateMatch(instance=instance, score=score, combined_text=combined_text))

    matches.sort(key=lambda item: item.score, reverse=True)
    return matches


__all__ = ["similarity_ratio", "rank_candidates", "score_candidates", "CandidateMatch"]
