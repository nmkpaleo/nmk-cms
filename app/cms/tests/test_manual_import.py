import os
from unittest.mock import patch

import django
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from cms.manual_import import (
    ManualImportError,
    build_accession_payload,
    build_reference_entries,
    find_media_for_row,
    import_manual_row,
)
from django.db import models

from cms.models import (
    Accession,
    AccessionFieldSlip,
    AccessionReference,
    AccessionRow,
    Collection,
    Element,
    FieldSlip,
    Locality,
    Media,
    NatureOfSpecimen,
    Storage,
)


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
        "storage_area": "Cabinet 5",
        "is_type_specimen": "Yes",
        "taxon": "Homo erectus",
        "family": "Hominidae",
        "genus": "Homo",
        "species": "erectus",
        "body_parts": "Rt. femur",
        "fragments": "19 bone frags ",
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
    assert field_slip["collection_date"]["interpreted"] == "2024-01-31"
    assert field_slip["field_number"]["interpreted"] == "FN-42"
    assert field_slip["verbatim_locality"]["interpreted"] == "Koobi Fora | Area 15"
    assert field_slip["verbatim_latitude"]["interpreted"] == "1.23"
    assert field_slip["verbatim_longitude"]["interpreted"] == "4.56"
    assert field_slip["verbatim_taxon"]["interpreted"].startswith("Homo erectus")

    row_entry = accession["rows"][0]
    assert row_entry["storage_area"]["interpreted"] == "Cabinet 5"
    nature = row_entry["natures"][0]
    assert nature["verbatim_element"]["interpreted"] == "Rt. femur"
    assert nature["fragments"]["interpreted"] == "19"


def test_build_accession_payload_supports_hyphenated_prefix():
    row = {
        "id": "1",
        "accession_number": "ER-30292",
    }

    payload = build_accession_payload([row])

    accession = payload["accessions"][0]
    assert accession["collection_abbreviation"]["interpreted"] == "KNM"
    assert accession["specimen_prefix_abbreviation"]["interpreted"] == "ER"
    assert accession["specimen_no"]["interpreted"] == 30292


@pytest.mark.parametrize(
    "coordinates, expected_lat, expected_lon",
    [
        ("N:03.86986 E:036.36386", "3.86986", "36.36386"),
        ("N: 03.86987 E: 036.36386", "3.86987", "36.36386"),
        ("35° 50' E, 02° 20' N", "2.333333", "35.833333"),
        ("35°50'E, 02°20'N ", "2.333333", "35.833333"),
    ],
)
def test_build_accession_payload_parses_coordinates_and_year_date(
    coordinates: str, expected_lat: str, expected_lon: str
):
    row = {
        "id": "2",
        "collection_id": "KNM",
        "accession_number": "ER 555",
        "field_number": "FN-55",
        "date": "1995",
        "storage_area": "Cabinet 6",
        "body_parts": "Specimen part",
        "coordinates": coordinates,
        "taxon": "Pan troglodytes",
    }

    payload = build_accession_payload([row])

    accession = payload["accessions"][0]
    field_slip = accession["field_slips"][0]
    assert field_slip["collection_date"]["interpreted"] == "1995-01-01"
    assert field_slip["verbatim_latitude"]["interpreted"] == expected_lat
    assert field_slip["verbatim_longitude"]["interpreted"] == expected_lon


def test_build_accession_payload_extracts_fragment_counts():
    row = {
        "id": "3",
        "collection_id": "KNM",
        "accession_number": "ER 777",
        "field_number": "FN-77",
        "body_parts": "Fragment",
        "fragments": "4 pieces ",
        "storage_area": "Cabinet 8",
    }

    payload = build_accession_payload([row])
    accession = payload["accessions"][0]
    row_entry = accession["rows"][0]
    nature = row_entry["natures"][0]
    assert nature["fragments"]["interpreted"] == "4"


def test_build_accession_payload_aggregates_consecutive_rows():
    base_row = {
        "id": "1",
        "collection_id": "KNM",
        "accession_number": "ER 123 A",
        "storage_area": "Cabinet 5",
        "body_parts": "Mandible",
        "is_published": "No",
        "field_number": "FN-001",
        "locality": "Base Camp",
    }
    extended_row = {
        "id": "2",
        "collection_id": "KNM",
        "accession_number": "ER 123 A-C",
        "storage_area": "Cabinet 5",
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


def test_build_reference_entries_extracts_page_and_defaults_year():
    reference_text = "Koobi Fora Research Project vol. 6 pg 246"

    entries = build_reference_entries(reference_text)

    assert len(entries) == 1
    entry = entries[0]
    assert entry["reference_first_author"]["interpreted"].startswith("Koobi Fora")
    assert entry["reference_title"]["interpreted"] == reference_text[:255]
    assert entry["reference_year"]["interpreted"] == "0000"
    assert entry["page"]["interpreted"] == "246"


def test_import_manual_row_updates_media_and_invokes_create(monkeypatch):
    collection = Collection.objects.filter(abbreviation="KNM").order_by("pk").first()
    if collection is None:
        collection = Collection.objects.create(abbreviation="KNM", description="Test collection")
    locality = Locality.objects.filter(abbreviation="ER").order_by("pk").first()
    if locality is None:
        locality = Locality.objects.create(abbreviation="ER", name="Koobi Fora")
    media = Media.objects.create(media_location="uploads/manual-import-7.jpg", file_name="manual-import-7.jpg")

    captured_payload = {}
    captured_kwargs = {}

    def _fake_create(media_obj, **kwargs):
        captured_payload.update(media_obj.ocr_data or {})
        captured_kwargs.update(kwargs)
        next_specimen = (
            Accession.objects.aggregate(max_no=models.Max("specimen_no")).get("max_no")
            or 1000
        ) + 1
        accession = Accession.objects.create(
            collection=collection,
            specimen_prefix=locality,
            specimen_no=next_specimen,
        )
        media_obj.accession = accession
        media_obj.accession_id = accession.pk
        return {"created": [{"accession_id": accession.pk}]}

    monkeypatch.setattr("cms.manual_import.create_accessions_from_media", _fake_create)

    row = {
        "id": "manual-import-7",
        "collection_id": "KNM",
        "accession_number": "ER 777",
        "storage_area": "Drawer 9",
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
    assert captured_kwargs.get("resolution_map") == {}
    assert result["created"]
    assert result["created"][0]["accession_id"] == media.accession_id

    accession = media.accession
    accession.refresh_from_db()
    assert accession.comment is not None
    assert "Manual QC import" in accession.comment
    assert "importer" in accession.comment
    assert "2024-03-02" in accession.comment


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
    captured_kwargs = {}

    def _fake_create(media_obj, **kwargs):
        call_count["value"] += 1
        captured_kwargs.update(kwargs)
        next_specimen = (
            Accession.objects.aggregate(max_no=models.Max("specimen_no")).get("max_no")
            or 2000
        ) + 1
        accession = Accession.objects.create(
            collection=collection,
            specimen_prefix=locality,
            specimen_no=next_specimen,
        )
        media_obj.accession = accession
        media_obj.accession_id = accession.pk
        return {"created": [{"accession_id": accession.pk}]}

    monkeypatch.setattr("cms.manual_import.create_accessions_from_media", _fake_create)

    rows = [
        {
            "id": "manual-import-8",
            "collection_id": "KNM",
            "accession_number": "ER 888 A",
            "storage_area": "Drawer 1",
            "body_parts": "Skull",
            "is_published": "No",
            "created_by": "importer",
            "created_on": "2024-03-03",
        },
        {
            "id": "manual-import-9",
            "collection_id": "KNM",
            "accession_number": "ER 888 A-C",
            "storage_area": "Drawer 1",
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
    assert result["created"]
    assert captured_kwargs.get("resolution_map") == {}
    assert result["created"][0]["accession_id"] == media_primary.accession_id

    accession = media_primary.accession
    accession.refresh_from_db()
    assert accession.comment is not None
    assert "Manual QC import" in accession.comment
    assert "importer" in accession.comment
    assert "2024-03-03" in accession.comment
    assert "2024-03-04" in accession.comment


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
            "storage_area": "Drawer 4",
            "field_number": "FN-100",
            "date": "1995",
            "body_parts": "Mandible",
            "taxon": "Pan troglodytes",
            "fragments": "19 bone frags ",
            "coordinates": "35°50'E, 02°20'N ",
            "is_published": "No",
        },
        {
            "id": "manual-import-11",
            "collection_id": "KNM",
            "accession_number": f"{accession_base} A-B",
            "storage_area": "Drawer 4",
            "field_number": "FN-101",
            "body_parts": "Tooth",
            "taxon": "Pan troglodytes",
            "fragments": "4 pieces ",
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

    accession = media_primary.accession
    assert accession is not None

    rows_qs = accession.accessionrow_set.select_related("storage").order_by("specimen_suffix")
    assert rows_qs.count() == 2
    storage_names = {row.storage.area for row in rows_qs if row.storage}
    assert storage_names == {"Drawer 4"}
    assert Storage.objects.filter(area__iexact="Drawer 4").exists()

    fragments = [
        nature.fragments
        for row in rows_qs
        for nature in NatureOfSpecimen.objects.filter(accession_row=row)
        if nature.fragments is not None
    ]
    assert fragments
    assert any(fragment and fragment > 0 for fragment in fragments)

    accession.refresh_from_db()
    slip_relation = (
        AccessionFieldSlip.objects.filter(accession=accession)
        .select_related("fieldslip")
        .order_by("fieldslip__field_number")
        .first()
    )
    assert slip_relation is not None
    field_slip = slip_relation.fieldslip
    assert isinstance(field_slip, FieldSlip)
    assert field_slip.collection_date is not None
    assert field_slip.collection_date.isoformat() == "1995-01-01"
    assert field_slip.verbatim_latitude == "2.333333"
    assert field_slip.verbatim_longitude == "35.833333"


def test_import_manual_row_creates_new_instance_for_existing_accession():
    collection = Collection.objects.filter(abbreviation="KNM").order_by("pk").first()
    if collection is None:
        collection = Collection.objects.create(abbreviation="KNM", description="Test collection")

    locality = Locality.objects.filter(abbreviation="ER").order_by("pk").first()
    if locality is None:
        locality = Locality.objects.create(abbreviation="ER", name="East River")

    specimen_no = (
        Accession.objects.filter(collection=collection, specimen_prefix=locality)
        .aggregate(max_no=models.Max("specimen_no"))
        .get("max_no")
        or 1000
    ) + 1

    existing = Accession.objects.create(
        collection=collection,
        specimen_prefix=locality,
        specimen_no=specimen_no,
        instance_number=1,
    )

    media = Media.objects.create(
        media_location="uploads/manual_qc/manual-dup-1.jpg",
        file_name="manual-dup-1.jpg",
    )

    rows = [
        {
            "id": "manual-dup-1",
            "collection_id": "KNM",
            "accession_number": f"ER {specimen_no} A",
            "storage_area": "Drawer 7",
            "field_number": "FD-200",
            "body_parts": "Femur",
            "is_published": "No",
        }
    ]

    queryset = Media.objects.filter(pk=media.pk)

    result = import_manual_row(rows, queryset=queryset)

    media.refresh_from_db()

    matching_accessions = Accession.objects.filter(
        collection=collection,
        specimen_prefix=locality,
        specimen_no=specimen_no,
    ).order_by("instance_number")

    assert matching_accessions.count() == 2
    newest = matching_accessions.last()
    assert newest.instance_number == existing.instance_number + 1
    assert media.accession_id == newest.pk
    assert result["created"]
    assert result["created"][0]["accession_id"] == newest.pk


def test_find_media_for_row_prefers_manual_qc_path():
    manual_media = Media.objects.create(
        media_location="uploads/manual_qc/1.jpg",
        file_name="1.jpg",
    )
    Media.objects.create(
        media_location="uploads/misc/1.jpg",
        file_name="1.jpg",
    )

    row = {"id": "1"}

    found = find_media_for_row(row)

    assert found.pk == manual_media.pk


def test_import_manual_row_creates_reference_links():
    collection, _ = Collection.objects.get_or_create(
        abbreviation="KNM", defaults={"description": "Test collection"}
    )
    locality, _ = Locality.objects.get_or_create(
        abbreviation="ER", defaults={"name": "Koobi Fora"}
    )

    media = Media.objects.create(
        media_location="uploads/manual_qc/25.jpg", file_name="25.jpg"
    )

    row = {
        "id": "25",
        "collection_id": collection.abbreviation,
        "accession_number": "ER 500 A",
        "field_number": "ER 88 4866",
        "date": "2021-01-14",
        "storage_area": "Cabinet 1",
        "is_type_specimen": "No",
        "taxon": "Cercopithecidae",
        "family": "Cercopithecidae",
        "genus": "Parapapio",
        "species": "medium/small",
        "body_parts": "1/2 p4 Lt.",
        "reference": "Leakey, L.S.B., 1964 Koobi Fora Research Project vol. 6 pg 246",
        "created_by": "admin",
        "created_on": "2021-01-14",
    }

    import_manual_row(row, queryset=Media.objects.filter(pk=media.pk))

    media.refresh_from_db()
    accession = media.accession

    assert accession is not None

    links = AccessionReference.objects.filter(accession=accession).select_related(
        "reference"
    )

    assert links.count() == 1
    link = links.first()
    assert link is not None
    assert link.page == "246"
    assert link.reference.first_author == "Leakey"
    assert link.reference.year == "1964"
    assert link.reference.title.startswith("Leakey")


def test_import_manual_row_sets_taxon_verbatim():
    collection, _ = Collection.objects.get_or_create(
        abbreviation="KNM", defaults={"description": "Test collection"}
    )
    locality, _ = Locality.objects.get_or_create(
        abbreviation="ER", defaults={"name": "Koobi Fora"}
    )

    media = Media.objects.create(
        media_location="uploads/manual_qc/26.jpg", file_name="26.jpg"
    )

    row = {
        "id": "26",
        "collection_id": collection.abbreviation,
        "accession_number": "ER 501 A",
        "storage_area": "Cabinet 2",
        "taxon": "Parapapio kindae",
        "family": "Cercopithecidae",
        "genus": "Parapapio",
        "species": "kindae",
        "body_parts": "Mandible",
    }

    import_manual_row(row, queryset=Media.objects.filter(pk=media.pk))

    media.refresh_from_db()
    accession = media.accession

    assert accession is not None

    accession_row = accession.accessionrow_set.first()
    assert accession_row is not None

    identification = accession_row.identification_set.first()
    assert identification is not None
    assert identification.taxon_verbatim == "Parapapio kindae"


def test_import_manual_row_uses_lowest_taxon_and_sets_qualifier():
    collection, _ = Collection.objects.get_or_create(
        abbreviation="KNM", defaults={"description": "Test collection"}
    )

    media = Media.objects.create(
        media_location="uploads/manual_qc/27.jpg", file_name="27.jpg"
    )

    row = {
        "id": "27",
        "collection_id": collection.abbreviation,
        "accession_number": "ER 502 A",
        "storage_area": "Cabinet 3",
        "family": "Cercopithecidae",
        "tribe": "Papionini",
        "genus": "cf. Parapapio",
        "body_parts": "Mandible",
    }

    import_manual_row(row, queryset=Media.objects.filter(pk=media.pk))

    media.refresh_from_db()
    accession = media.accession

    assert accession is not None

    accession_row = accession.accessionrow_set.first()
    assert accession_row is not None

    identification = accession_row.identification_set.first()
    assert identification is not None
    assert identification.taxon_verbatim == "Parapapio"
    assert identification.identification_qualifier == "cf."


def test_import_manual_row_requires_taxon_verbatim():
    collection, _ = Collection.objects.get_or_create(
        abbreviation="KNM", defaults={"description": "Test collection"}
    )

    media = Media.objects.create(
        media_location="uploads/manual_qc/29.jpg", file_name="29.jpg"
    )

    row = {
        "id": "29",
        "collection_id": collection.abbreviation,
        "accession_number": "ER 504 A",
        "storage_area": "Cabinet 5",
        "body_parts": "Mandible",
    }

    import_manual_row(row, queryset=Media.objects.filter(pk=media.pk))

    media.refresh_from_db()
    accession = media.accession

    assert accession is not None

    accession_row = accession.accessionrow_set.first()
    assert accession_row is not None

    assert accession_row.identification_set.count() == 0


def test_import_manual_row_sets_verbatim_identification_from_field_slip_taxon():
    collection, _ = Collection.objects.get_or_create(
        abbreviation="KNM", defaults={"description": "Test collection"}
    )

    media = Media.objects.create(
        media_location="uploads/manual_qc/28.jpg", file_name="28.jpg"
    )

    row = {
        "id": "28",
        "collection_id": collection.abbreviation,
        "accession_number": "ER 503 A",
        "storage_area": "Cabinet 4",
        "family": "Cercopithecidae",
        "tribe": "Papionini",
        "genus": "cf. Parapapio",
        "body_parts": "Mandible",
    }

    import_manual_row(row, queryset=Media.objects.filter(pk=media.pk))

    media.refresh_from_db()
    accession = media.accession

    assert accession is not None

    accession_row = accession.accessionrow_set.first()
    assert accession_row is not None

    identification = accession_row.identification_set.first()
    assert identification is not None
    assert (
        identification.verbatim_identification
        == "Cercopithecidae | Papionini | cf. Parapapio"
    )


def test_import_manual_row_reuses_existing_element():
    collection = Collection.objects.filter(abbreviation="KNM").order_by("pk").first()
    if collection is None:
        collection = Collection.objects.create(abbreviation="KNM", description="Test collection")

    locality = Locality.objects.filter(abbreviation="ER").order_by("pk").first()
    if locality is None:
        locality = Locality.objects.create(abbreviation="ER", name="East River")

    media = Media.objects.create(
        media_location="uploads/manual_qc/manual-element-1.jpg",
        file_name="manual-element-1.jpg",
    )

    parent_element, _ = Element.objects.get_or_create(name="-Undefined")
    femur, _ = Element.objects.get_or_create(
        name="Femur", defaults={"parent_element": parent_element}
    )
    initial_count = Element.objects.count()

    row = {
        "id": "manual-element-1",
        "collection_id": "KNM",
        "accession_number": "ER 321",
        "storage_area": "Drawer 1",
        "field_number": "FD-300",
        "body_parts": "Femur",
        "taxon": "Pan troglodytes",
    }

    import_manual_row(row, queryset=Media.objects.filter(pk=media.pk))

    assert Element.objects.count() == initial_count

    media.refresh_from_db()
    accession = media.accession
    assert accession is not None
    nature = NatureOfSpecimen.objects.filter(accession_row__accession=accession).first()
    assert nature is not None
    assert nature.element_id == femur.id
    assert nature.verbatim_element == "Femur"


def test_import_manual_row_uses_placeholder_when_element_missing():
    collection = Collection.objects.filter(abbreviation="KNM").order_by("pk").first()
    if collection is None:
        collection = Collection.objects.create(abbreviation="KNM", description="Test collection")

    locality = Locality.objects.filter(abbreviation="ER").order_by("pk").first()
    if locality is None:
        locality = Locality.objects.create(abbreviation="ER", name="East River")

    media = Media.objects.create(
        media_location="uploads/manual_qc/manual-element-2.jpg",
        file_name="manual-element-2.jpg",
    )

    placeholder, _ = Element.objects.get_or_create(name="-Undefined")
    initial_count = Element.objects.count()

    row = {
        "id": "manual-element-2",
        "collection_id": "KNM",
        "accession_number": "ER 322",
        "storage_area": "Drawer 2",
        "field_number": "FD-301",
        "body_parts": "Novel element description",
        "taxon": "Pan troglodytes",
    }

    import_manual_row(row, queryset=Media.objects.filter(pk=media.pk))

    assert Element.objects.count() == initial_count

    media.refresh_from_db()
    accession = media.accession
    assert accession is not None
    nature = NatureOfSpecimen.objects.filter(accession_row__accession=accession).first()
    assert nature is not None
    assert nature.element_id == placeholder.id
    assert nature.verbatim_element == "Novel element description"
