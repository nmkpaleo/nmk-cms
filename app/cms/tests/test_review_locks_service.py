import uuid
from datetime import timedelta

import pytest
from crum import set_current_user
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from cms.models import SpecimenListPage, SpecimenListPDF
from cms.services.review_locks import acquire_review_lock, lock_is_expired, release_review_lock

pytestmark = pytest.mark.django_db


@pytest.fixture
def reviewer(django_user_model):
    user = django_user_model.objects.create_user(username=f"reviewer-{uuid.uuid4().hex}", password="x")
    set_current_user(user)
    return user


@pytest.fixture
def other_reviewer(django_user_model):
    return django_user_model.objects.create_user(username=f"other-{uuid.uuid4().hex}", password="x")


@pytest.fixture(autouse=True)
def cleanup_current_user():
    try:
        yield
    finally:
        set_current_user(None)


def _create_page(user) -> SpecimenListPage:
    set_current_user(user)
    pdf_file = SimpleUploadedFile("specimen.pdf", b"%PDF-1.4", content_type="application/pdf")
    pdf = SpecimenListPDF.objects.create(
        source_label="Specimen List",
        original_filename="specimen.pdf",
        stored_file=pdf_file,
    )
    return SpecimenListPage.objects.create(pdf=pdf, page_number=1)


def test_lock_is_expired_handles_missing_and_recent_timestamps():
    assert lock_is_expired(None) is True
    assert lock_is_expired(timezone.now()) is False
    assert lock_is_expired(timezone.now() - timedelta(hours=2)) is True


def test_acquire_review_lock_sets_reviewer_and_status(reviewer):
    page = _create_page(reviewer)

    locked = acquire_review_lock(page_id=page.id, reviewer=reviewer)
    locked.refresh_from_db()

    assert locked.assigned_reviewer_id == reviewer.id
    assert locked.locked_at is not None
    assert locked.pipeline_status == SpecimenListPage.PipelineStatus.IN_REVIEW
    assert locked.review_status == SpecimenListPage.ReviewStatus.IN_REVIEW


def test_acquire_review_lock_does_not_override_active_foreign_lock(reviewer, other_reviewer):
    page = _create_page(reviewer)
    page.assigned_reviewer = reviewer
    page.locked_at = timezone.now()
    page.pipeline_status = SpecimenListPage.PipelineStatus.IN_REVIEW
    page.review_status = SpecimenListPage.ReviewStatus.IN_REVIEW
    page.save(update_fields=["assigned_reviewer", "locked_at", "pipeline_status", "review_status"])

    locked = acquire_review_lock(page_id=page.id, reviewer=other_reviewer, allow_override=False)
    assert locked.assigned_reviewer_id == reviewer.id


def test_release_review_lock_clears_lock_for_owner(reviewer):
    page = _create_page(reviewer)
    acquire_review_lock(page_id=page.id, reviewer=reviewer)

    released = release_review_lock(page_id=page.id, reviewer=reviewer)
    released.refresh_from_db()

    assert released.assigned_reviewer is None
    assert released.locked_at is None
    assert released.pipeline_status == SpecimenListPage.PipelineStatus.PENDING
    assert released.review_status == SpecimenListPage.ReviewStatus.PENDING
