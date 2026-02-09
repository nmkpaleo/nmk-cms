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
    Media,
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
    set_current_user(reviewer)
    Element.objects.create(name="Femur")
    set_current_user(None)
    specimen_no = uuid.uuid4().int % 1000000
    field_number = f"FS-{specimen_no}"
    pdf = _build_pdf()
    page = SpecimenListPage.objects.create(pdf=pdf, page_number=1)
    image_file = SimpleUploadedFile("page.png", b"fake-image-data", content_type="image/png")
    with override_settings(MEDIA_ROOT=tmp_path):
        page.image_file.save("page.png", image_file, save=True)

    row = SpecimenListRowCandidate.objects.create(
        page=page,
        row_index=0,
        data={
            "accession_number": f"ER {specimen_no}",
            "field_number": field_number,
            "taxon": "Homo",
            "element": "femur",
            "locality": "Koobi Fora",
            "review_comment": "QC check ok.",
            "red_dot": True,
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

    result_payload = row.data.get("_import_result")
    assert result_payload
    assert result_payload["accession_id"] is not None
    assert row.data.get("_draft")

    accession = Accession.objects.get(pk=result_payload["accession_id"])
    assert accession.is_published is True
    assert accession.collection.abbreviation == "KNM"
    assert accession.specimen_prefix.abbreviation == "ER"
    assert accession.specimen_no == specimen_no

    assert AccessionRow.objects.filter(accession=accession).exists()
    assert FieldSlip.objects.filter(field_number=field_number).exists()
    assert AccessionFieldSlip.objects.filter(accession=accession).exists()
    assert Identification.objects.filter(accession_row__accession=accession).exists()
    assert NatureOfSpecimen.objects.filter(accession_row__accession=accession).exists()
    assert Media.objects.filter(accession=accession).exists()

    fieldslip_link = AccessionFieldSlip.objects.filter(accession=accession).first()
    assert fieldslip_link.notes == "QC check ok."

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


def test_approve_row_creates_nature_of_specimen_with_verbatim_element():
    reviewer = _build_reviewer()
    _ensure_collection_and_locality(reviewer)
    pdf = _build_pdf()
    page = SpecimenListPage.objects.create(pdf=pdf, page_number=1)
    specimen_no = uuid.uuid4().int % 1000000
    row = SpecimenListRowCandidate.objects.create(
        page=page,
        row_index=0,
        data={
            "accession_number": f"KNM-ER {specimen_no}",
            "taxon": "Homo",
            "element": "clavicle",
            "side": "left",
            "portion": "proximal",
            "condition": "fragment",
        },
    )

    approve_row(row=row, reviewer=reviewer)

    row.refresh_from_db()
    nature = NatureOfSpecimen.objects.get(accession_row__accession__specimen_no=specimen_no)
    assert nature.verbatim_element == "clavicle"
    assert nature.side == "left"
    assert nature.portion == "proximal"
    assert nature.condition == "fragment"
