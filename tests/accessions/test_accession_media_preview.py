"""Tests for accession detail layout and media preview assets."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import django
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DB_ENGINE", "django.db.backends.sqlite3")
django.setup()

TEMPLATES_ROOT = Path(settings.BASE_DIR, "cms", "templates", "cms")
STATIC_ROOT = Path(settings.BASE_DIR, "cms", "static", "cms")


def _read_template(relative: str) -> str:
    return Path(TEMPLATES_ROOT, relative).read_text(encoding="utf-8")


def _read_static(relative: str) -> str:
    return Path(STATIC_ROOT, relative).read_text(encoding="utf-8")


def test_preview_panel_sections_are_ordered_for_three_area_layout() -> None:
    content = _read_template("partials/accession_preview_panel.html")

    specimen_index = content.index('id="accession-specimens-heading"')
    horizon_index = content.index('id="accession-horizon-heading"')
    assert specimen_index < horizon_index, "Horizon block must render after specimen table"

    for heading in (
        'id="accession-fieldslip-links-heading"',
        'id="accession-fieldslips-heading"',
    ):
        assert heading in content, f"Expected to find {heading} heading in preview panel"
        assert (
            specimen_index < content.index(heading) < horizon_index
        ), f"{heading} should remain between specimen details and horizon section"


def test_media_preview_triggers_define_required_data_attributes() -> None:
    content = _read_template("partials/accession_preview_panel.html")
    trigger_links = re.findall(
        r"<a[^>]+class=\"[^\"]*media-preview-trigger[^\"]*\"[^>]*>",
        content,
    )
    assert trigger_links, "Expected at least one media preview trigger anchor"
    for link in trigger_links:
        assert "data-media-preview=" in link, "Preview trigger must expose preview URL"
        assert "data-media-alt=" in link, "Preview trigger must expose alt text"


def test_media_hover_preview_container_declares_accessibility_attributes() -> None:
    content = _read_template("accession_detail.html")
    normalised = " ".join(content.split())
    assert 'id="media-hover-preview"' in normalised
    assert 'class="accession-media-hover-preview' in normalised
    assert 'role="tooltip"' in normalised
    assert 'aria-hidden="true"' in normalised
    assert 'id="media-hover-preview-img"' in normalised


def test_media_preview_assets_enforce_large_screen_centre_behaviour() -> None:
    script = _read_static("js/accession_media_preview.js")
    assert "CENTERED_CLASS = 'is-centered'" in script
    assert "previewContainer.classList.add(CENTERED_CLASS);" in script
    assert "previewContainer.classList.remove(CENTERED_CLASS);" in script
    assert "window.matchMedia(LARGE_SCREEN_QUERY)" in script

    stylesheet = Path(settings.BASE_DIR, "cms", "static", "css", "style.css").read_text(
        encoding="utf-8"
    )
    assert ".accession-media-hover-preview" in stylesheet
    assert "max-width: 720px" in stylesheet
