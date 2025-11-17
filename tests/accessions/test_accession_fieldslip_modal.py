"""Regression tests for accession field slip modal and overlay styling."""

from __future__ import annotations

import os
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
STATIC_ROOT = Path(settings.BASE_DIR, "cms", "static")


def _read_template(relative: str) -> str:
    return Path(TEMPLATES_ROOT, relative).read_text(encoding="utf-8")


def _read_static(relative: str) -> str:
    return Path(STATIC_ROOT, relative).read_text(encoding="utf-8")


def test_fieldslip_modal_markup_exposes_accessibility_attributes() -> None:
    detail_template = _read_template("accession_detail.html")
    preview_partial = _read_template("partials/accession_preview_panel.html")

    modal_markup = " ".join(detail_template.split())
    actions_markup = " ".join(preview_partial.split())

    assert "id=\"fieldSlipModal\"" in modal_markup
    assert "role=\"dialog\"" in modal_markup
    assert "aria-modal=\"true\"" in modal_markup
    assert "aria-labelledby=\"fieldSlipModalTitle\"" in modal_markup
    assert "id=\"fieldSlipFrame\"" in modal_markup
    assert "id=\"fieldSlipModalCloseButton\"" in modal_markup
    assert "aria-hidden=\"true\"" in modal_markup, "Modal should default to hidden"

    assert "id=\"accession-fieldslip-actions\"" in actions_markup
    assert "aria-controls=\"fieldSlipModal\"" in actions_markup


def test_modal_styles_raise_zindex_above_select2() -> None:
    stylesheet = _read_static("css/style.css")

    assert ".w3-modal" in stylesheet, "Modal class should be styled"
    assert "z-index: 11000" in stylesheet, "Modal should sit above Select2 widgets"
    assert "z-index: 11001" in stylesheet, "Modal content should exceed overlay"
