"""Public interface for the CMS merge framework."""
from .constants import MergeStrategy
from .engine import merge_records
from .mixins import MergeMixin
from .registry import MERGE_REGISTRY, register_merge_rules
from .signals import merge_failed

__all__ = [
    "MergeMixin",
    "MergeStrategy",
    "MERGE_REGISTRY",
    "register_merge_rules",
    "merge_records",
    "MergeLog",
    "merge_failed",
]


def __getattr__(name: str):
    if name == "MergeLog":
        from cms.models import MergeLog

        return MergeLog
    raise AttributeError(name)
