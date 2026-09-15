import uuid

import pytest
from crum import set_current_user
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch

from cms.models import SpecimenListPage, SpecimenListPageOCR, SpecimenListPDF
from cms.tasks import run_specimen_list_ocr_queue, run_specimen_list_row_extraction_queue

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_user(django_user_model):
    user = django_user_model.objects.create_user(username=f"staff-{uuid.uuid4().hex}", password="x")
    set_current_user(user)
    return user


@pytest.fixture(autouse=True)
def cleanup_current_user():
    try:
        yield
    finally:
        set_current_user(None)


def _create_page(user, *, with_image=True, classified=True, details_page=True):
    set_current_user(user)
    pdf = SpecimenListPDF.objects.create(
        source_label="Batch",
        original_filename="batch.pdf",
        stored_file=SimpleUploadedFile("batch.pdf", b"%PDF-1.4", content_type="application/pdf"),
    )
    page = SpecimenListPage.objects.create(
        pdf=pdf,
        page_number=1,
        classification_status=(
            SpecimenListPage.ClassificationStatus.CLASSIFIED if classified else SpecimenListPage.ClassificationStatus.PENDING
        ),
        page_type=(
            SpecimenListPage.PageType.SPECIMEN_LIST_DETAILS if details_page else SpecimenListPage.PageType.UNKNOWN
        ),
        pipeline_status=SpecimenListPage.PipelineStatus.CLASSIFIED,
    )
    if with_image:
        page.image_file.save("page.png", SimpleUploadedFile("page.png", b"img", content_type="image/png"), save=True)
    return page


@patch("cms.tasks.run_specimen_list_raw_ocr")
def test_run_specimen_list_ocr_queue_marks_missing_image_as_failure(mock_raw_ocr, staff_user):
    page = _create_page(staff_user, with_image=False)

    summary = run_specimen_list_ocr_queue(ids=[page.id])

    assert summary.successes == 0
    assert summary.failures == 1
    assert any("missing image file" in err for err in summary.errors)
    mock_raw_ocr.assert_not_called()


@patch("cms.tasks.run_specimen_list_raw_ocr")
def test_run_specimen_list_ocr_queue_success_sets_ocr_done(mock_raw_ocr, staff_user):
    page = _create_page(staff_user, with_image=True)

    summary = run_specimen_list_ocr_queue(ids=[page.id])
    page.refresh_from_db()

    assert summary.successes == 1
    assert summary.failures == 0
    assert page.pipeline_status == SpecimenListPage.PipelineStatus.OCR_DONE
    mock_raw_ocr.assert_called_once()


@patch("cms.tasks.run_specimen_list_row_extraction")
def test_row_extraction_queue_requires_raw_ocr_entry(mock_extract, staff_user):
    page = _create_page(staff_user, with_image=True, details_page=True)

    summary = run_specimen_list_row_extraction_queue(ids=[page.id])

    assert summary.successes == 0
    assert summary.failures == 1
    assert any("missing raw OCR" in err for err in summary.errors)
    mock_extract.assert_not_called()


@patch("cms.tasks.run_specimen_list_row_extraction")
def test_row_extraction_queue_success_sets_extracted(mock_extract, staff_user):
    mock_extract.return_value = [{"row": 1}]
    page = _create_page(staff_user, with_image=True, details_page=True)
    SpecimenListPageOCR.objects.create(page=page, raw_text="raw", bounding_boxes=[])

    summary = run_specimen_list_row_extraction_queue(ids=[page.id])
    page.refresh_from_db()

    assert summary.successes == 1
    assert summary.failures == 0
    assert page.pipeline_status == SpecimenListPage.PipelineStatus.EXTRACTED
    mock_extract.assert_called_once()
