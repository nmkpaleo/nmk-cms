"""Test package initialisation for cms.tests."""

import sys
from types import ModuleType

from .upload_processing import UploadProcessingTests

_upload_module = ModuleType("cms.tests.UploadProcessingTests")
_upload_module.UploadProcessingTests = UploadProcessingTests
sys.modules.setdefault("cms.tests.UploadProcessingTests", _upload_module)

__all__ = ["UploadProcessingTests"]
