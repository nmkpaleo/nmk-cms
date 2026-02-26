import pytest
from django.conf import settings
from pathlib import Path

pytestmark = pytest.mark.django_db

DETAIL_TEMPLATES = [
    (
        "accession_detail.html",
        [
            "<main class=\"w3-container w3-margin-top\" role=\"main\">",
            "aria-labelledby=\"accession-details-heading\"",
            "w3-table-all",
        ],
    ),
    (
        "accession_row_detail.html",
        [
            "aria-labelledby=\"specimen-details-heading\"",
            "w3-table-all",
            "fa-solid fa-dna",
        ],
    ),
    (
        "drawerregister_detail.html",
        [
            "aria-labelledby=\"drawer-details-heading\"",
            "fa-folder-open",
        ],
    ),
    (
        "fieldslip_detail.html",
        [
            "aria-labelledby=\"fieldslip-details-heading\"",
            "w3-card",
            "fa-solid fa-pen-to-square",
        ],
    ),
    (
        "locality_detail.html",
        [
            "aria-labelledby=\"locality-details-heading\"",
            "w3-card",
        ],
    ),
    (
        "place_detail.html",
        [
            "aria-labelledby=\"place-details-heading\"",
            "w3-card",
            "fa-solid fa-pen-to-square",
        ],
    ),
    (
        "preparation_detail.html",
        [
            "aria-labelledby=\"preparation-details-heading\"",
            "w3-table-all",
            "fa-solid fa-photo-film",
        ],
    ),
    (
        "reference_detail.html",
        [
            "aria-labelledby=\"reference-details-heading\"",
            "w3-table-all",
            "fa-solid fa-boxes-stacked",
        ],
    ),
]


def load_template(name: str) -> str:
    template_path = Path(settings.BASE_DIR, "cms", "templates", "cms", name)
    return template_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("template_name, snippets", DETAIL_TEMPLATES)
def test_detail_templates_use_w3_layout(template_name: str, snippets):
    content = load_template(template_name)
    assert '{% extends "base_generic.html" %}' in content
    for snippet in snippets:
        assert snippet in content


def test_accession_preview_panel_structure():
    content = Path(
        settings.BASE_DIR, "cms", "templates", "cms", "partials", "accession_preview_panel.html"
    ).read_text(encoding="utf-8")
    assert "<section class=\"w3-margin-top\" aria-labelledby=\"accession-summary-heading\">" in content
    assert "w3-table-all" in content
    assert "fa-solid fa-photo-film" in content
