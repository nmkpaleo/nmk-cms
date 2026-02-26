from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from cms.models import SpecimenListPDF, SpecimenListPage
from cms.tasks import (
    _coerce_confidence,
    _normalize_page_type,
    _set_pipeline_status,
    classify_pending_specimen_pages,
)


@pytest.mark.django_db
@patch("cms.management.commands.classify_specimen_pages.classify_pending_specimen_pages")
def test_classify_specimen_pages_command_outputs_summary(mock_classify, capsys):
    mock_classify.return_value = type("S", (), {"errors": ["page 1: bad"], "successes": 2, "failures": 1, "total": 3})()
    call_command("classify_specimen_pages", "--limit", "5", "--force")
    out = capsys.readouterr().out
    assert "page 1: bad" in out
    assert "Classified 2 pages with 1 failures (total 3)." in out


@pytest.mark.django_db
@patch("cms.management.commands.process_specimen_list_ocr.run_specimen_list_ocr_queue")
@patch("cms.management.commands.process_specimen_list_ocr.run_specimen_list_row_extraction_queue")
def test_process_specimen_list_ocr_command_runs_both_stages(mock_rows, mock_raw, capsys):
    mock_raw.return_value = type("S", (), {"errors": [], "successes": 1, "failures": 0, "total": 1})()
    mock_rows.return_value = type("S", (), {"errors": ["row failed"], "successes": 0, "failures": 1, "total": 1})()

    call_command("process_specimen_list_ocr", "--stage", "both", "--limit", "2")
    out = capsys.readouterr().out
    assert "OCR: 1 succeeded, 0 failed (total 1)." in out
    assert "row failed" in out
    assert "Rows: 0 succeeded, 1 failed (total 1)." in out


@pytest.mark.django_db
@patch("cms.management.commands.process_specimen_list_pdfs.process_specimen_list_pdf")
def test_process_specimen_list_pdfs_command_processes_uploaded_items(mock_process, capsys):
    SpecimenListPDF.objects.create(original_filename="a.pdf", status=SpecimenListPDF.Status.UPLOADED)
    SpecimenListPDF.objects.create(original_filename="b.pdf", status=SpecimenListPDF.Status.ERROR)

    call_command("process_specimen_list_pdfs")
    out = capsys.readouterr().out
    assert mock_process.call_count == 2
    assert "Processed 2 specimen list PDFs." in out


def test_task_helper_functions_coerce_and_normalize():
    assert _coerce_confidence(None) is None
    assert str(_coerce_confidence("-1")) == "0"
    assert str(_coerce_confidence("2")) == "1"
    assert str(_coerce_confidence("0.25")) == "0.25"
    assert _normalize_page_type(" typewritten_text ") == SpecimenListPage.PageType.TYPED_TEXT
    assert _normalize_page_type("unknown") is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "initial, expected",
    [
        (SpecimenListPage.PipelineStatus.PENDING, SpecimenListPage.PipelineStatus.OCR_DONE),
        (SpecimenListPage.PipelineStatus.APPROVED, SpecimenListPage.PipelineStatus.APPROVED),
    ],
)
def test_set_pipeline_status_respects_terminal_states(initial, expected):
    page = SpecimenListPage(pipeline_status=initial)
    _set_pipeline_status(page, SpecimenListPage.PipelineStatus.OCR_DONE)
    assert page.pipeline_status == expected


@pytest.mark.django_db
@patch("cms.tasks.classify_specimen_list_page")
def test_classify_pending_specimen_pages_marks_missing_file_as_failure(mock_classify, tmp_path):
    pdf = SpecimenListPDF.objects.create(original_filename="source.pdf")
    page = SpecimenListPage.objects.create(
        pdf=pdf,
        page_number=1,
        classification_status=SpecimenListPage.ClassificationStatus.PENDING,
    )

    summary = classify_pending_specimen_pages(ids=[page.id])
    page.refresh_from_db()

    assert summary.failures == 1
    assert summary.successes == 0
    assert "missing image file" in summary.errors[0]
    assert page.classification_status == SpecimenListPage.ClassificationStatus.FAILED
    mock_classify.assert_not_called()


@pytest.mark.django_db
@patch("cms.tasks.classify_specimen_list_page")
def test_classify_pending_specimen_pages_success_path(mock_classify, tmp_path):
    mock_classify.return_value = {
        "page_type": "specimen_list_details",
        "confidence": "0.88",
        "notes": "  valid  ",
    }
    pdf = SpecimenListPDF.objects.create(original_filename="source.pdf")
    page = SpecimenListPage.objects.create(
        pdf=pdf,
        page_number=1,
        classification_status=SpecimenListPage.ClassificationStatus.PENDING,
    )
    image = SimpleUploadedFile("page.png", b"img", content_type="image/png")
    with patch("django.conf.settings.MEDIA_ROOT", str(tmp_path)):
        page.image_file.save("page.png", image, save=True)

    summary = classify_pending_specimen_pages(ids=[page.id])
    page.refresh_from_db()

    assert summary.successes == 1
    assert summary.failures == 0
    assert page.classification_status == SpecimenListPage.ClassificationStatus.CLASSIFIED
    assert page.page_type == SpecimenListPage.PageType.SPECIMEN_LIST_DETAILS
    assert str(page.classification_confidence).startswith("0.88")
    assert page.classification_notes == "valid"
