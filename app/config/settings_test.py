"""Test settings overrides for pytest.

Keeps production defaults in ``config.settings`` while forcing a local SQLite
DB in CI/dev test runs so tests don't require a MySQL service.
"""

from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}
