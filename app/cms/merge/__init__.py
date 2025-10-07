"""Public interface for the CMS merge framework."""
from .constants import MergeStrategy
from .mixins import MergeMixin
from .registry import MERGE_REGISTRY, register_merge_rules

__all__ = ["MergeMixin", "MergeStrategy", "MERGE_REGISTRY", "register_merge_rules"]
