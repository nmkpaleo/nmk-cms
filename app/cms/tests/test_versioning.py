from pathlib import Path

from django.conf import settings

from config.versioning import get_application_version


def test_get_application_version_uses_env(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "v9.9.9")
    assert get_application_version() == "v9.9.9"


def test_base_template_displays_application_version_variable():
    template_path = Path(settings.BASE_DIR, "cms", "templates", "base_generic.html")
    content = template_path.read_text(encoding="utf-8")

    assert "Version" in content
    assert "{{ application_version }}" in content
