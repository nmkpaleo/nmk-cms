import pytest
from django.conf import settings
from pathlib import Path

DETAIL_TEMPLATES = [
    (
        "accession_detail.html",
        [
            "<main class=\"w3-container w3-margin-top accession-detail-page\" role=\"main\">",
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
            "drawer-detail-page",
            "aria-labelledby=\"drawer-details-heading\"",
            "fa-folder-open",
        ],
    ),
    (
        "fieldslip_detail.html",
        [
            "fieldslip-detail-page",
            "aria-labelledby=\"fieldslip-details-heading\"",
            "fieldslip-data-table",
            "fa-solid fa-pen-to-square",
        ],
    ),
    (
        "locality_detail.html",
        [
            "locality-detail-page",
            "aria-labelledby=\"locality-details-heading\"",
            "locality-overview-table",
        ],
    ),
    (
        "place_detail.html",
        [
            "place-detail-page",
            "aria-labelledby=\"place-details-heading\"",
            "place-overview-table",
            "fa-solid fa-pen-to-square",
        ],
    ),
    (
        "preparation_detail.html",
        [
            "preparation-detail-page",
            "aria-labelledby=\"preparation-details-heading\"",
            "preparation-data-table",
            "fa-solid fa-photo-film",
        ],
    ),
    (
        "storage_detail.html",
        [
            "storage-detail-page",
            "storage-tabs-heading",
            "storage_list",
        ],
    ),
    (
        "reference_detail.html",
        [
            "reference-detail-page",
            "aria-labelledby=\"reference-details-heading\"",
            "reference-metadata-table",
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
    assert "<section class=\"w3-margin-top accession-summary-panel\" aria-labelledby=\"accession-summary-heading\">" in content
    assert "w3-table-all" in content
    assert "fa-solid fa-photo-film" in content


def test_accession_filter_taxonomy_fields_follow_requested_order():
    content = load_template("accession_list.html")
    fields = (
        "{{ filter.form.tribe }}",
        "{{ filter.form.genus }}",
        "{{ filter.form.species }}",
        "{{ filter.form.element }}",
    )

    positions = [content.index(field) for field in fields]
    assert positions == sorted(positions)


def test_accession_detail_sections_follow_collection_workflow_order():
    content = Path(
        settings.BASE_DIR, "cms", "templates", "cms", "partials", "accession_preview_panel.html"
    ).read_text(encoding="utf-8")
    headings = (
        'id="accession-summary-heading"',
        'id="accession-specimens-heading"',
        'id="accession-fieldslip-links-heading"',
        'id="accession-horizon-heading"',
        'id="accession-references-heading"',
        'id="accession-media-heading"',
    )
    positions = [content.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert "accession-detail-sections" in content
    assert "accession-overview-table" in content


def test_locality_detail_sections_follow_collection_workflow_order():
    content = load_template("locality_detail.html")
    headings = (
        'id="locality-metadata-heading"',
        'id="locality-places-heading"',
    )
    positions = [content.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert positions[-1] < content.index('section_id="locality-accessions"')
    assert "locality-detail-section" in content
    assert "locality-overview-table" in content


def test_place_detail_sections_follow_collection_workflow_order():
    content = load_template("place_detail.html")
    headings = (
        'id="place-metadata-heading"',
        'id="place-children-heading"',
        'id="place-related-heading"',
        'id="place-accessions-heading"',
    )
    positions = [content.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert "place-detail-section" in content
    assert "place-overview-table" in content


def test_reference_list_header_links_use_contrast_class():
    content = load_template("reference_list.html")
    assert "reference-list-page" in content
    assert "sort='first_author'" in content

    stylesheet = Path(settings.BASE_DIR, "cms", "static", "css", "style.css").read_text(
        encoding="utf-8"
    )
    assert ".reference-list-page table.w3-table-all thead th a" in stylesheet
    assert "color: var(--nmk-white) !important" in stylesheet


def test_reference_detail_sections_are_ordered_tables():
    content = load_template("reference_detail.html")
    headings = (
        'id="reference-metadata-heading"',
        'id="reference-publication-heading"',
        'id="reference-accessions-heading"',
    )
    positions = [content.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert content.count("reference-metadata-table") == 2
    assert "reference-detail-section" in content


def test_fieldslip_detail_sections_use_ordered_tables():
    content = load_template("fieldslip_detail.html")
    headings = (
        'id="fieldslip-primary-context-heading"',
        'id="fieldslip-sedimentary-heading"',
    )
    positions = [content.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert positions[-1] < content.index('section_id="fieldslip-related-accessions"')
    assert content.count("fieldslip-data-table") == 2
    assert 'section_class="fieldslip-detail-section"' in content


def test_drawer_detail_sections_use_ordered_tables():
    content = load_template("tabs/drawerregister_details.html")
    headings = (
        'id="drawer-overview-heading"',
        'id="drawer-scans-heading"',
        'id="drawer-localities-heading"',
        'id="drawer-taxa-heading"',
    )
    positions = [content.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert content.count("drawer-detail-section") == 4
    assert "w3-table-all" in content


def test_storage_detail_sections_use_ordered_tables():
    content = load_template("tabs/storage_details.html")
    headings = (
        'id="storage-details-overview"',
        'id="storage-children-heading"',
        'id="storage-specimens-heading"',
    )
    positions = [content.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert content.count("storage-detail-section") == 3
    assert "storage-data-table" in content
    assert "specimen_page_obj.previous_page_number" in content


def test_preparation_list_keeps_filters_and_create_permission():
    content = load_template("preparation_list.html")
    assert "preparation-list-page" in content
    assert 'id="prepFilterPanel"' in content
    assert "filter.form.accession_label" in content
    assert "filter.form.approval_status" in content
    assert "preparation_create" in content
    assert "preparation_detail" in content


def test_preparation_detail_sections_are_ordered_tables():
    content = load_template("preparation_detail.html")
    headings = (
        'id="preparation-overview-heading"',
        'id="preparation-method-heading"',
        'id="preparation-approval-heading"',
        'id="preparation-history-heading"',
        'id="preparation-media-heading"',
    )
    positions = [content.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert content.count("preparation-data-table") == 3
    assert "preparation_approve" in content
    assert "preparation_upload_media_form" in content


def test_review_pages_use_shared_review_styles_without_losing_actions():
    review_templates = {
        "cms/specimen_list_queue.html": (
            "specimen-review-queue",
            "review-filter-panel",
            "review-data-table",
        ),
        "cms/specimen_list_page_review.html": (
            "specimen-page-review",
            "review-image-panel",
            'name="action" value="approve"',
            'name="action" value="reject"',
        ),
        "cms/qc/wizard_base.html": (
            "media-qc-review-page",
            "data-controller=\"qc-rows\"",
        ),
        "cms/qc/history.html": (
            "media-qc-history-page",
            "media-qc-history-table",
        ),
        "cms/preparation_approve.html": (
            "preparation-review-page",
            "preparation-approve-form",
        ),
    }
    project_template_root = Path(settings.BASE_DIR, "templates")
    for template_name, snippets in review_templates.items():
        if template_name.startswith("cms/"):
            template_path = Path(settings.BASE_DIR, "cms", "templates", template_name)
        else:
            template_path = Path(project_template_root, template_name)
        content = template_path.read_text(encoding="utf-8")
        for snippet in snippets:
            assert snippet in content, f"Expected {snippet!r} in {template_name}"

    row_review = Path(
        project_template_root, "cms/specimen_list_row_review.html"
    ).read_text(encoding="utf-8")
    assert "specimen-row-review" in row_review
    assert 'name="action" value="approve"' in row_review
    assert 'name="action" value="reject"' in row_review
