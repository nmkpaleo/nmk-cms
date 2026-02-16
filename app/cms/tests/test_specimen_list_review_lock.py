import uuid

import pytest
from crum import set_current_user
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from app.cms.models import SpecimenListPage, SpecimenListPDF

pytestmark = pytest.mark.django_db


@pytest.fixture
def reviewer():
    user_model = get_user_model()
    return user_model.objects.create(username=f"reviewer-{uuid.uuid4().hex}")


@pytest.fixture(autouse=True)
def cleanup_current_user():
    try:
        yield
    finally:
        set_current_user(None)


def _create_pdf() -> SpecimenListPDF:
    pdf_file = SimpleUploadedFile("specimen.pdf", b"%PDF-1.4", content_type="application/pdf")
    return SpecimenListPDF.objects.create(
        source_label="Specimen List",
        original_filename="specimen.pdf",
        stored_file=pdf_file,
    )


def test_review_status_history_tracks_transitions(reviewer):
    pdf = _create_pdf()
    page = SpecimenListPage.objects.create(pdf=pdf, page_number=1)

    set_current_user(reviewer)
    page.review_status = SpecimenListPage.ReviewStatus.IN_REVIEW
    page.assigned_reviewer = reviewer
    page.locked_at = timezone.now()
    page.save()

    history = page.history.latest()
    assert history.review_status == SpecimenListPage.ReviewStatus.IN_REVIEW
    assert history.assigned_reviewer_id == reviewer.id
    assert history.locked_at is not None


def test_review_lock_release_is_recorded(reviewer):
    pdf = _create_pdf()
    page = SpecimenListPage.objects.create(
        pdf=pdf,
        page_number=1,
        assigned_reviewer=reviewer,
        locked_at=timezone.now(),
        review_status=SpecimenListPage.ReviewStatus.IN_REVIEW,
    )

    page.assigned_reviewer = None
    page.locked_at = None
    page.review_status = SpecimenListPage.ReviewStatus.PENDING
    page.save()

    history = page.history.latest()
    assert history.assigned_reviewer_id is None
    assert history.locked_at is None
    assert history.review_status == SpecimenListPage.ReviewStatus.PENDING
