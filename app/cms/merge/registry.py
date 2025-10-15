"""Simple registry utilities for storing merge specific rules."""
from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, MutableMapping, Type

from django.conf import settings
from django.db import models

from .constants import MergeStrategy

logger = logging.getLogger(__name__)

MERGE_REGISTRY: MutableMapping[Type[models.Model], Dict[str, Any]] = {}


def register_merge_rules(
    model: Type[models.Model],
    *,
    fields: Mapping[str, MergeStrategy | str] | None = None,
    relations: Mapping[str, Any] | None = None,
) -> None:
    """Register custom merge rules for a model class."""

    if not getattr(settings, "MERGE_TOOL_FEATURE", False):
        logger.debug(
            "Merge tool disabled; skipping registry update for %s", model
        )
        return

    record = MERGE_REGISTRY.setdefault(model, {"fields": {}, "relations": {}})
    if fields:
        record["fields"].update(fields)
    if relations:
        record["relations"].update(relations)

    if hasattr(model, "merge_fields") and isinstance(model.merge_fields, MutableMapping):
        model.merge_fields.update(record["fields"])
    if hasattr(model, "relation_strategies") and isinstance(model.relation_strategies, MutableMapping):
        model.relation_strategies.update(record["relations"])
