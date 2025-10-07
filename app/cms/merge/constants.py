"""Constants and enumerations used by the merge framework."""
from __future__ import annotations

from enum import Enum


class MergeStrategy(str, Enum):
    """Strategies that describe how conflicting values should be reconciled."""

    LAST_WRITE = "last_write"
    """Always prefer the value from the most recently saved record."""

    PREFER_NON_NULL = "prefer_non_null"
    """Choose the first non-empty value when merging two records."""

    CONCAT_TEXT = "concat_text"
    """Concatenate text values with a separator to preserve both inputs."""

    WHITELIST = "whitelist"
    """Limit merge candidates to an allow-listed field or relation set."""

    CUSTOM = "custom"
    """Use project specific logic registered in the merge registry."""

    USER_PROMPT = "user_prompt"
    """Defer to a human to resolve the field during the merge session."""


#: Default strategy used when a field does not define explicit behaviour.
DEFAULT_FIELD_STRATEGY: MergeStrategy = MergeStrategy.PREFER_NON_NULL

#: Default strategy that can be used for relations when no override is defined.
DEFAULT_RELATION_STRATEGY: MergeStrategy = MergeStrategy.LAST_WRITE

#: Convenience tuple for widgets that need to display available strategies.
MERGE_STRATEGY_CHOICES = tuple((strategy.value, strategy.name.title()) for strategy in MergeStrategy)
