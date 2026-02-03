from __future__ import annotations

from typing import Any

from django.conf import settings


def _object_to_dict(obj: Any) -> dict[str, object]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    for attr in ("model_dump", "to_dict", "dict"):
        method = getattr(obj, attr, None)
        if callable(method):
            try:
                data = method()
            except Exception:  # pragma: no cover - defensive in case API changes
                continue
            if isinstance(data, dict):
                return data
    return {}


def build_usage_payload(response: Any, model: str) -> dict[str, object | None]:
    """Return pricing and token usage metadata for an OpenAI response."""

    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
    completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
    total_tokens = getattr(usage, "total_tokens", 0) if usage else 0

    if not total_tokens and (prompt_tokens or completion_tokens):
        total_tokens = prompt_tokens + completion_tokens

    pricing = getattr(settings, "OPENAI_PRICING", {}) or {}
    rates = pricing.get(model, {}) or {}
    prompt_rate = rates.get("prompt")
    completion_rate = rates.get("completion")

    def _cost(tokens: int, rate: float | None) -> float | None:
        if rate is None or tokens is None:
            return None
        return round(tokens * rate, 6)

    prompt_cost = _cost(prompt_tokens, prompt_rate)
    completion_cost = _cost(completion_tokens, completion_rate)
    total_cost: float | None = None
    if prompt_cost is not None or completion_cost is not None:
        total_cost = round((prompt_cost or 0.0) + (completion_cost or 0.0), 6)

    usage_dict = _object_to_dict(usage)
    remaining_quota = None
    for key in ("remaining_quota", "remaining_quota_usd", "remaining_budget", "remaining_budget_usd"):
        value = usage_dict.get(key)
        if value not in (None, ""):
            remaining_quota = value
            break

    payload = {
        "model": getattr(response, "model", model) or model,
        "request_id": getattr(response, "id", None),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "prompt_cost_usd": prompt_cost,
        "completion_cost_usd": completion_cost,
        "total_cost_usd": total_cost,
    }

    if remaining_quota not in (None, ""):
        payload["remaining_quota_usd"] = remaining_quota

    return payload


def add_usage_timing(payload: dict[str, object | None], elapsed_seconds: float | None) -> dict[str, object | None]:
    if elapsed_seconds is None:
        return payload
    updated = payload.copy()
    updated.setdefault("processing_seconds", round(elapsed_seconds, 3))
    return updated
