import json
import uuid

import pytest
from crum import set_current_user
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.test import override_settings

from cms.admin import NatureOfSpecimenAdmin
from cms.models import (
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
from cms.services.review_approval import (
    approve_page,
    approve_row,
    infer_nature_side_portion_from_element_text,
)

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
    fieldslip = FieldSlip.objects.get(field_number=field_number)
    assert fieldslip.comment == "QC check ok."

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




def test_approve_row_parses_taxon_qualifier_and_preserves_verbatim():
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
            "taxon": "cf Homo habilis",
        },
    )

    approve_row(row=row, reviewer=reviewer)

    identification = Identification.objects.get(accession_row__accession__specimen_no=specimen_no)
    assert identification.taxon_verbatim == "Homo habilis"
    assert identification.taxon == "Homo habilis"
    assert identification.identification_qualifier == "cf."
    assert identification.verbatim_identification == "cf. Homo habilis"

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


class NatureOfSpecimenAdminCompatibilityTests(TestCase):
    def test_admin_changelist_renders_inferred_values_and_history(self):
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
                "element": "Lt clavicle prox",
                "condition": "fragment",
            },
        )

        approve_row(row=row, reviewer=reviewer)

        nature = NatureOfSpecimen.objects.get(accession_row__accession__specimen_no=specimen_no)
        self.assertEqual(nature.side, "left")
        self.assertEqual(nature.portion, "proximal")

        history_entry = nature.history.latest()
        self.assertEqual(history_entry.side, "left")
        self.assertEqual(history_entry.portion, "proximal")

        staff = get_user_model().objects.create_superuser(
            username=f"admin-{uuid.uuid4().hex}",
            email="admin@example.com",
            password="pass",
        )
        request = RequestFactory().get("/admin/cms/natureofspecimen/")
        request.user = staff
        model_admin = NatureOfSpecimenAdmin(NatureOfSpecimen, AdminSite())

        response = model_admin.changelist_view(request)
        response.render()
        self.assertEqual(response.status_code, 200)


class InferNatureSidePortionTests:
    """Unit tests for side/portion inference from element text tokens."""

    @pytest.mark.parametrize(
        "element_text,expected_side,expected_portion",
        [
            # Single side tokens (various cases and abbreviations)
            ("Lt femur", "left", None),
            ("lt femur", "left", None),
            ("LT femur", "left", None),
            ("L femur", "left", None),
            ("Left femur", "left", None),
            ("left femur", "left", None),
            ("Rt humerus", "right", None),
            ("rt humerus", "right", None),
            ("RT humerus", "right", None),
            ("R humerus", "right", None),
            ("Right humerus", "right", None),
            ("right humerus", "right", None),
            # Single portion tokens
            ("femur Dist", None, "distal"),
            ("femur dist", None, "distal"),
            ("femur DIST", None, "distal"),
            ("femur Distal", None, "distal"),
            ("femur distal", None, "distal"),
            ("femur Prox", None, "proximal"),
            ("femur prox", None, "proximal"),
            ("femur PROX", None, "proximal"),
            ("femur Proximal", None, "proximal"),
            ("femur proximal", None, "proximal"),
            # Combined side and portion
            ("Lt femur Dist", "left", "distal"),
            ("Rt humerus Prox", "right", "proximal"),
            ("Left tibia Distal", "left", "distal"),
            ("Right ulna Proximal", "right", "proximal"),
            # Tokens with periods
            ("Lt. femur", "left", None),
            ("Rt. femur Dist.", "right", "distal"),
            # Multiple same tokens (should still work)
            ("Lt Lt femur", "left", None),
            ("femur Dist Dist", None, "distal"),
            # No tokens
            ("femur", None, None),
            ("humerus", None, None),
            ("", None, None),
            (None, None, None),
            # Ambiguous cases (conflicting tokens)
            ("Lt Rt femur", None, None),
            ("Rt Lt femur", None, None),
            ("femur Dist Prox", None, None),
            ("femur Prox Dist", None, None),
            ("Lt Rt femur Dist Prox", None, None),
            # Edge cases with extra whitespace
            ("  Lt   femur  ", "left", None),
            ("  femur  Dist  ", None, "distal"),
        ],
    )
    def test_infer_side_portion_from_tokens(
        self, element_text, expected_side, expected_portion
    ):
        """Test inference of side/portion from element text tokens."""
        side, portion = infer_nature_side_portion_from_element_text(element_text)
        assert side == expected_side, f"Expected side={expected_side}, got {side}"
        assert portion == expected_portion, f"Expected portion={expected_portion}, got {portion}"

    def test_inference_returns_canonical_lowercase(self):
        """Verify canonical output values match NatureOfSpecimen usage."""
        # Test that all side variants map to lowercase canonical forms
        test_cases = [
            ("Lt femur", "left"),
            ("LT femur", "left"),
            ("L femur", "left"),
            ("Left femur", "left"),
            ("Rt femur", "right"),
            ("RT femur", "right"),
            ("R femur", "right"),
            ("Right femur", "right"),
        ]
        for element_text, expected_side in test_cases:
            side, _ = infer_nature_side_portion_from_element_text(element_text)
            assert side == expected_side
            assert side.islower() if side else True

        # Test that all portion variants map to lowercase canonical forms
        test_cases = [
            ("femur Dist", "distal"),
            ("femur DIST", "distal"),
            ("femur Distal", "distal"),
            ("femur Prox", "proximal"),
            ("femur PROX", "proximal"),
            ("femur Proximal", "proximal"),
        ]
        for element_text, expected_portion in test_cases:
            _, portion = infer_nature_side_portion_from_element_text(element_text)
            assert portion == expected_portion
            assert portion.islower() if portion else True


def test_side_portion_inference_disabled_by_feature_flag():
    """Verify inference can be disabled via settings flag."""
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
            "element": "Lt femur Dist",
            "condition": "fragment",
        },
    )

    # Disable inference via settings
    with override_settings(SPECIMEN_LIST_ENABLE_SIDE_PORTION_INFERENCE=False):
        approve_row(row=row, reviewer=reviewer)

    nature = NatureOfSpecimen.objects.get(accession_row__accession__specimen_no=specimen_no)
    # When disabled, side and portion should not be inferred
    assert nature.side is None
    assert nature.portion is None


def test_side_portion_inference_does_not_overwrite_explicit_values():
    """Verify inference never overwrites manually-provided side/portion values."""
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
            # Element says "Lt femur Dist" but explicit values say otherwise
            "element": "Lt femur Dist",
            "side": "right",  # Explicit value contradicts element
            "portion": "proximal",  # Explicit value contradicts element
            "condition": "fragment",
        },
    )

    approve_row(row=row, reviewer=reviewer)

    nature = NatureOfSpecimen.objects.get(accession_row__accession__specimen_no=specimen_no)
    # Explicit values should be preserved, not overwritten by inference
    assert nature.side == "right"
    assert nature.portion == "proximal"


def test_side_portion_inference_from_element_corrected():
    """Verify inference uses element_corrected when available."""
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
            "element": "femur",  # Original has no side/portion
            "element_corrected": "Rt femur Prox",  # Corrected version has them
            "condition": "fragment",
        },
    )

    approve_row(row=row, reviewer=reviewer)

    nature = NatureOfSpecimen.objects.get(accession_row__accession__specimen_no=specimen_no)
    # Should use element_corrected for inference
    assert nature.side == "right"
    assert nature.portion == "proximal"
