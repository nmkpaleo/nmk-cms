"""Pytest bootstrap helpers.

Pytest-django owns Django initialization via ``DJANGO_SETTINGS_MODULE`` in
``pytest.ini``. This module intentionally avoids calling ``django.setup()`` or
setting Django env vars so plugin startup order remains intact.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

LEGACY_SUBMODULE_ALIASES: tuple[str, ...] = (
    "models",
    "filters",
    "forms",
    "tests",
    "views",
    "urls",
    "resources",
)


def _install_legacy_app_cms_aliases() -> None:
    """Map legacy ``app.cms`` imports to canonical ``cms`` modules.

    This shim only touches ``sys.modules`` aliases and is invoked during pytest
    configuration, after pytest-django has initialized Django.
    """

    cms_module = importlib.import_module("cms")

    app_namespace = sys.modules.get("app")
    if app_namespace is None:
        app_namespace = ModuleType("app")
        cms_path = next(iter(getattr(cms_module, "__path__", [])), None)
        app_namespace.__path__ = [str(Path(cms_path).parent)] if cms_path else []
        sys.modules["app"] = app_namespace

    sys.modules.setdefault("app.cms", cms_module)

    for submodule in LEGACY_SUBMODULE_ALIASES:
        module = importlib.import_module(f"cms.{submodule}")
        sys.modules.setdefault(f"app.cms.{submodule}", module)


def pytest_configure() -> None:
    """Install legacy import aliases without duplicating pytest-django setup."""

    _install_legacy_app_cms_aliases()
