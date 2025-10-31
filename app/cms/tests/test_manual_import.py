import os
from unittest.mock import patch

import django
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from cms.manual_import import (
    ManualImportError,
    build_accession_payload,
    find_media_for_row,
    import_manual_row,
)
from django.db import models

from cms.models import Collection, Locality, Media, Accession


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DB_ENGINE", "django.db.backends.sqlite3")
django.setup()


@pytest.fixture(scope="session", autouse=True)
def _migrate_db():
    call_command("migrate", run_syncdb=True, verbosity=0)


@pytest.fixture(autouse=True)
def _current_user_patch():
    user_model = get_user_model()
    user, _ = user_model.objects.get_or_create(
        username="importer",
        defaults={"is_staff": True, "email": "importer@example.com"},
    )
    with patch("cms.models.get_current_user", return_value=user):
        yield user


def test_build_accession_payload_maps_row_fields():
    row = {
        "id": "1",
        "collection_id": "KNM",
        "accession_number": "ER 123 A",
        "field_number": "FN-42",
        "field_number_printed": "FN-42A",
        "date": "2024-01-31",
        "shelf": "Cabinet 5",
        "is_type_specimen": "Yes",
        "taxon": "Homo erectus",
        "family": "Hominidae",
        "genus": "Homo",
        "species": "erectus",
        "body_parts": "Rt. femur",
        "fragments": "3",
        "coordinates": "1.23, 4.56",
        "locality": "Koobi Fora",
        "site_area": "Area 15",
        "formation": "Nachukui",
        "member_horizon_level": "Kalochoro",
        "photo_id": "P-100",
        "is_published": "Yes",
        "reference": "Leakey, 1964, Homo erectus p. 12",
        "other": "Verified manually",
    }

    payload = build_accession_payload([row])

    assert payload["card_type"] == "accession_card"
    accession = payload["accessions"][0]
    assert accession["collection_abbreviation"]["interpreted"] == "KNM"
    assert accession["specimen_prefix_abbreviation"]["interpreted"] == "ER"
    assert accession["specimen_no"]["interpreted"] == 123
    assert accession["specimen_suffix"]["interpreted"] == "A"
    assert accession["published"]["interpreted"] == "Yes"
    assert accession["type_status"]["interpreted"] == "Type"

    field_slip = accession["field_slips"][0]
    assert field_slip["field_number"]["interpreted"] == "FN-42"
    assert field_slip["verbatim_locality"]["interpreted"] == "Koobi Fora | Area 15"
    assert field_slip["verbatim_latitude"]["interpreted"] == "1.23"
    assert field_slip["verbatim_longitude"]["interpreted"] == "4.56"
    assert field_slip["verbatim_taxon"]["interpreted"].startswith("Homo erectus")

    row_entry = accession["rows"][0]
    assert row_entry["storage_area"]["interpreted"] == "Cabinet 5"
    nature = row_entry["natures"][0]
    assert nature["verbatim_element"]["interpreted"] == "Rt. femur"
    assert nature["fragments"]["interpreted"] == "3"


def test_build_accession_payload_aggregates_consecutive_rows():
    base_row = {
        "id": "1",
        "collection_id": "KNM",
        "accession_number": "ER 123 A",
        "shelf": "Cabinet 5",
        "body_parts": "Mandible",
        "is_published": "No",
        "field_number": "FN-001",
        "locality": "Base Camp",
    }
    extended_row = {
        "id": "2",
        "collection_id": "KNM",
        "accession_number": "ER 123 A-C",
        "shelf": "Cabinet 5",
        "body_parts": "Tooth",
        "is_published": "Yes",
        "field_number": "FN-002",
        "locality": "Base Camp",
    }

    payload = build_accession_payload([base_row, extended_row])

    accession = payload["accessions"][0]
    assert accession["specimen_suffix"]["interpreted"] == "A-C"
    assert len(accession["field_slips"]) == 2
    assert {
        slip["field_number"]["interpreted"] for slip in accession["field_slips"]
    } == {"FN-001", "FN-002"}
    row_suffixes = [entry["specimen_suffix"]["interpreted"] for entry in accession["rows"]]
    assert row_suffixes == ["A", "B", "C"]
    element_values = {
        nature["verbatim_element"]["interpreted"]
        for entry in accession["rows"]
        for nature in entry["natures"]
    }
    assert "Mandible" in element_values
    assert "Tooth" in element_values
    assert accession["published"]["interpreted"] == "Yes"


def test_find_media_for_row_matches_filename():
    media = Media.objects.create(media_location="uploads/manual-test-1.jpg", file_name="manual-test-1.jpg")

    result = find_media_for_row({"id": "manual-test-1"}, queryset=Media.objects.filter(pk=media.pk))

    assert result.pk == media.pk


def test_find_media_for_row_missing_raises():
    with pytest.raises(ManualImportError):
        find_media_for_row({"id": "999"}, queryset=[])


def test_build_accession_payload_treats_null_marker_as_blank():
    rows = [
        {
            "id": "10",
            "collection_id": "KNM",
            "accession_number": "ER 999 A",
            "field_number": "\\N",
            "locality": "\\N",
            "body_parts": "\\N",
            "reference": "\\N",
            "other": "\\N",
        }
    ]

    payload = build_accession_payload(rows)

    accession = payload["accessions"][0]
    field_slip = accession["field_slips"][0]
    assert field_slip["field_number"] == {}
    assert accession["references"] == []
    assert accession["additional_notes"] == []


def test_import_manual_row_updates_media_and_invokes_create(monkeypatch):
    collection = Collection.objects.filter(abbreviation="KNM").order_by("pk").first()
    if collection is None:
        collection = Collection.objects.create(abbreviation="KNM", description="Test collection")
    locality = Locality.objects.filter(abbreviation="ER").order_by("pk").first()
    if locality is None:
        locality = Locality.objects.create(abbreviation="ER", name="Koobi Fora")
    media = Media.objects.create(media_location="uploads/manual-import-7.jpg", file_name="manual-import-7.jpg")

    captured_payload = {}

    def _fake_create(media_obj):
        captured_payload.update(media_obj.ocr_data or {})
        return {"created": [{"accession_id": 1}]}

    monkeypatch.setattr("cms.manual_import.create_accessions_from_media", _fake_create)

    row = {
        "id": "manual-import-7",
        "collection_id": "KNM",
        "accession_number": "ER 777",
        "shelf": "Drawer 9",
        "taxon": "Test taxon",
        "body_parts": "Skull",
        "is_published": "No",
        "created_by": "importer",
        "created_on": "2024-03-02",
    }

    result = import_manual_row(row, queryset=Media.objects.filter(pk=media.pk))

    media.refresh_from_db()
    assert media.qc_status == Media.QCStatus.APPROVED
    assert media.ocr_status == Media.OCRStatus.COMPLETED
    assert media.expert_checked_by.username == "importer"
    manual_metadata = media.ocr_data["_manual_import"]
    assert manual_metadata["row_id"] == "manual-import-7"
    assert manual_metadata["row_ids"] == ["manual-import-7"]
    assert manual_metadata["group_size"] == 1
    assert captured_payload["card_type"] == "accession_card"
    assert result == {"created": [{"accession_id": 1}]}


def test_import_manual_row_groups_consecutive_rows(monkeypatch):
    collection = Collection.objects.filter(abbreviation="KNM").order_by("pk").first()
    if collection is None:
        collection = Collection.objects.create(abbreviation="KNM", description="Test collection")
    locality = Locality.objects.filter(abbreviation="ER").order_by("pk").first()
    if locality is None:
        locality = Locality.objects.create(abbreviation="ER", name="Koobi Fora")
    media_primary = Media.objects.create(media_location="uploads/manual-import-8.jpg", file_name="manual-import-8.jpg")
    media_secondary = Media.objects.create(media_location="uploads/manual-import-9.jpg", file_name="manual-import-9.jpg")

    call_count = {"value": 0}

    def _fake_create(media_obj):
        call_count["value"] += 1
        return {"created": [{"accession_id": 7}]}

    monkeypatch.setattr("cms.manual_import.create_accessions_from_media", _fake_create)

    rows = [
        {
            "id": "manual-import-8",
            "collection_id": "KNM",
            "accession_number": "ER 888 A",
            "shelf": "Drawer 1",
            "body_parts": "Skull",
            "is_published": "No",
            "created_by": "importer",
            "created_on": "2024-03-03",
        },
        {
            "id": "manual-import-9",
            "collection_id": "KNM",
            "accession_number": "ER 888 A-C",
            "shelf": "Drawer 1",
            "body_parts": "Femur",
            "is_published": "Yes",
            "created_by": "importer",
            "created_on": "2024-03-04",
        },
    ]

    queryset = Media.objects.filter(pk__in=[media_primary.pk, media_secondary.pk])

    result = import_manual_row(rows, queryset=queryset)

    media_primary.refresh_from_db()
    media_secondary.refresh_from_db()

    assert call_count["value"] == 1
    assert media_primary.qc_status == Media.QCStatus.APPROVED
    assert media_secondary.qc_status == Media.QCStatus.APPROVED
    assert media_primary.ocr_data["_manual_import"]["row_ids"] == [
        "manual-import-8",
        "manual-import-9",
    ]
    assert media_secondary.ocr_data["_manual_import"]["primary"] is False
    rows_payload = media_primary.ocr_data["accessions"][0]["rows"]
    suffixes = [entry["specimen_suffix"]["interpreted"] for entry in rows_payload]
    assert suffixes == ["A", "B", "C"]
    assert result == {"created": [{"accession_id": 7}]}


def test_import_manual_row_links_all_media_to_accession():
    collection = Collection.objects.filter(abbreviation="KNM").order_by("pk").first()
    if collection is None:
        collection = Collection.objects.create(abbreviation="KNM", description="Test collection")

    next_number = (
        Accession.objects.aggregate(max_no=models.Max("specimen_no")).get("max_no") or 900
    ) + 1
    accession_base = f"ER {next_number}"

    media_primary = Media.objects.create(media_location="uploads/manual-import-10.jpg", file_name="manual-import-10.jpg")
    media_secondary = Media.objects.create(media_location="uploads/manual-import-11.jpg", file_name="manual-import-11.jpg")

    rows = [
        {
            "id": "manual-import-10",
            "collection_id": "KNM",
            "accession_number": f"{accession_base} A",
            "shelf": "Drawer 4",
            "field_number": "FN-100",
            "body_parts": "Mandible",
            "is_published": "No",
        },
        {
            "id": "manual-import-11",
            "collection_id": "KNM",
            "accession_number": f"{accession_base} A-B",
            "shelf": "Drawer 4",
            "field_number": "FN-101",
            "body_parts": "Tooth",
            "is_published": "No",
        },
    ]

    queryset = Media.objects.filter(pk__in=[media_primary.pk, media_secondary.pk])

    result = import_manual_row(rows, queryset=queryset)

    media_primary.refresh_from_db()
    media_secondary.refresh_from_db()

    assert result["created"], result
    assert media_primary.accession_id is not None
    assert media_secondary.accession_id == media_primary.accession_id
    assert result["created"]
