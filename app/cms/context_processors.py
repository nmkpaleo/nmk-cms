"""Context processors used across CMS templates."""
from __future__ import annotations

from django.conf import settings


def merge_feature_flag(request):
    """Expose the merge tool rollout flag to templates."""

    return {"merge_tool_enabled": getattr(settings, "MERGE_TOOL_FEATURE", False)}
