"""Helpers for resolving the application version shown in the UI."""

from __future__ import annotations

import os
import subprocess


def get_application_version() -> str:
    """Return the best available application version string.

    Resolution order:
    1. ``APP_VERSION`` environment variable (recommended for deployed builds).
    2. Git tag/description when running from a git checkout.
    3. Short git SHA if a tag is not available.
    4. Fallback to ``"dev"``.
    """

    configured_version = os.getenv("APP_VERSION", "").strip()
    if configured_version:
        return configured_version

    for cmd in (
        ["git", "describe", "--tags", "--always", "--dirty"],
        ["git", "rev-parse", "--short", "HEAD"],
    ):
        try:
            value = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
        except (FileNotFoundError, OSError, subprocess.CalledProcessError):
            value = ""
        if value:
            return value

    return "dev"

