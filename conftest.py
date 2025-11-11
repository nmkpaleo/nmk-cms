import importlib
import os
import sys
from types import ModuleType

PROJECT_ROOT = os.path.dirname(__file__)
APP_DIR = os.path.join(PROJECT_ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# Ensure the legacy "app.cms" namespace resolves to the Django app module.
if "app" not in sys.modules:
    namespace_pkg = ModuleType("app")
    namespace_pkg.__path__ = [APP_DIR]
    sys.modules["app"] = namespace_pkg

cms_module = importlib.import_module("cms")
sys.modules.setdefault("app.cms", cms_module)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DB_ENGINE", "django.db.backends.sqlite3")
os.environ.setdefault("DB_NAME", os.path.join(APP_DIR, "db.sqlite3"))

import django  # noqa: E402  (import after environment configured)

django.setup()

# Mirror commonly imported submodules for backwards compatibility.
for submodule in ("models", "filters", "forms", "tests", "views", "urls", "resources"):
    try:
        module = importlib.import_module(f"cms.{submodule}")
    except ModuleNotFoundError:
        continue
    sys.modules.setdefault(f"app.cms.{submodule}", module)
