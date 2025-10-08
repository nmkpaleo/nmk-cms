"""Simple registry utilities for storing merge specific rules."""
from __future__ import annotations

from typing import Any, Dict, Mapping, MutableMapping, Type

from django.db import models

from .constants import MergeStrategy

MERGE_REGISTRY: MutableMapping[Type[models.Model], Dict[str, Any]] = {}


def register_merge_rules(
    model: Type[models.Model],
    *,
    fields: Mapping[str, MergeStrategy | str] | None = None,
    relations: Mapping[str, MergeStrategy | str] | None = None,
) -> None:
    """Register custom merge rules for a model class."""

    record = MERGE_REGISTRY.setdefault(model, {"fields": {}, "relations": {}})
    if fields:
        record["fields"].update(fields)
    if relations:
        record["relations"].update(relations)

    if hasattr(model, "merge_fields") and isinstance(model.merge_fields, MutableMapping):
        model.merge_fields.update(record["fields"])
    if hasattr(model, "relation_strategies") and isinstance(model.relation_strategies, MutableMapping):
        model.relation_strategies.update(record["relations"])
