import json
import uuid

import pytest
from crum import set_current_user
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from app.cms.models import (
    Accession,
    AccessionFieldSlip,
    AccessionRow,
    Collection,
    Element,
    FieldSlip,
    Identification,
    Locality,
    NatureOfSpecimen,
    SpecimenListPage,
    SpecimenListPDF,
    SpecimenListRowCandidate,
)
from app.cms.services.review_approval import approve_page, approve_row

pytestmark = pytest.mark.django_db


def _build_pdf() -> SpecimenListPDF:
    pdf_file = SimpleUploadedFile("specimen.pdf", b"%PDF-1.4", content_type="application/pdf")
    return SpecimenListPDF.objects.create(
        source_label="Specimen List",
        original_filename="specimen.pdf",
        stored_file=pdf_file,
    )


def _build_reviewer():
    return get_user_model().objects.create(username=f"reviewer-{uuid.uuid4().hex}")


def _ensure_collection_and_locality(user):
    set_current_user(user)
    collection, _ = Collection.objects.get_or_create(
        abbreviation="KNM",
        defaults={"description": "Kenya National Museums"},
    )
    locality, _ = Locality.objects.get_or_create(
        abbreviation="ER",
        defaults={"name": "East Rudolf"},
    )
    set_current_user(None)
    return collection, locality


def test_approve_page_creates_records_and_moves_image(tmp_path):
    reviewer = _build_reviewer()
    _ensure_collection_and_locality(reviewer)
    Element.objects.create(name="Femur")
    pdf = _build_pdf()
    page = SpecimenListPage.objects.create(pdf=pdf, page_number=1)
    image_file = SimpleUploadedFile("page.png", b"fake-image-data", content_type="image/png")
    with override_settings(MEDIA_ROOT=tmp_path):
        page.image_file.save("page.png", image_file, save=True)

    row = SpecimenListRowCandidate.objects.create(
        page=page,
        row_index=0,
        data={
            "accession_number": "KNM-ER 123",
            "field_number": "FS-1",
            "taxon": "Homo",
            "element": "femur",
            "locality": "Koobi Fora",
        },
    )

    with override_settings(MEDIA_ROOT=tmp_path):
        results = approve_page(page=page, reviewer=reviewer)

    assert results
    page.refresh_from_db()
    row.refresh_from_db()

    assert page.pipeline_status == SpecimenListPage.PipelineStatus.APPROVED
    assert page.review_status == SpecimenListPage.ReviewStatus.APPROVED
    assert "/pages/approved/" in page.image_file.name

    assert Accession.objects.count() == 1
    assert AccessionRow.objects.count() == 1
    assert FieldSlip.objects.count() == 1
    assert AccessionFieldSlip.objects.count() == 1
    assert Identification.objects.count() == 1
    assert NatureOfSpecimen.objects.count() == 1

    result_payload = row.data.get("_import_result")
    assert result_payload
    assert result_payload["accession_id"] is not None

    summary_line = [line for line in page.classification_notes.splitlines() if line][-1]
    summary = json.loads(summary_line)
    assert summary["results"]


def test_approve_row_records_errors():
    reviewer = _build_reviewer()
    _ensure_collection_and_locality(reviewer)
    pdf = _build_pdf()
    page = SpecimenListPage.objects.create(pdf=pdf, page_number=1)
    row = SpecimenListRowCandidate.objects.create(page=page, row_index=0, data={})

    result = approve_row(row=row, reviewer=reviewer)

    row.refresh_from_db()
    assert result.errors
    assert row.data.get("_import_result")
