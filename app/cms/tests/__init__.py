"""Helpers for Django test discovery in ``cms.tests`` package."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_MODULE_NAME = "cms._tests_module"
_tests_module = sys.modules.get(_MODULE_NAME)
if _tests_module is None:
    _tests_path = Path(__file__).resolve().parent.parent / "tests.py"
    _spec = importlib.util.spec_from_file_location(_MODULE_NAME, _tests_path)
    if _spec is None or _spec.loader is None:  # pragma: no cover - importlib guard
        raise ImportError("Unable to load cms.tests module for aliases")
    _tests_module = importlib.util.module_from_spec(_spec)
    sys.modules[_MODULE_NAME] = _tests_module
    _spec.loader.exec_module(_tests_module)

_alias = ModuleType("cms.tests.UploadProcessingTests")
_alias.UploadProcessingTests = _tests_module.UploadProcessingTests
sys.modules.setdefault("cms.tests.UploadProcessingTests", _alias)

UploadProcessingTests = _tests_module.UploadProcessingTests

__all__ = ["UploadProcessingTests"]
