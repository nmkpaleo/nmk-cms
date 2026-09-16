from __future__ import annotations

from types import SimpleNamespace

import pytest
from crum import set_current_user
from django.contrib.auth import get_user_model

from cms import resources as cms_resources
from cms.models import Taxon, TaxonStatus


class _Dataset:
    def __init__(self, headers=None):
        self.headers = list(headers or [])


class _FakeQS:
    def __init__(self, items):
        self._items = items

    def count(self):
        return len(self._items)

    def first(self):
        return self._items[0] if self._items else None


class _FakeManager:
    def __init__(self, items):
        self._items = items

    def filter(self, **_kwargs):
        return _FakeQS(self._items)


def test_dayfirst_datetime_widget_parses_both_formats_and_rejects_invalid():
    widget = cms_resources.DayFirstDateTimeWidget()
    assert widget.clean("") is None
    parsed = widget.clean("01/02/2024 13:45")
    assert parsed is not None
    parsed_seconds = widget.clean("01/02/2024 13:45:10")
    assert parsed_seconds is not None
    with pytest.raises(ValueError, match="Incorrect datetime format"):
        widget.clean("2024-02-01")


def test_accession_resource_dehydrate_helpers(monkeypatch):
    resource = cms_resources.AccessionResource()
    obj = SimpleNamespace(
        collection=SimpleNamespace(abbreviation="KNM"),
        specimen_prefix=SimpleNamespace(abbreviation="ER"),
        specimen_no=123,
    )
    assert resource.dehydrate_accession(obj) == "KNM-ER 123"

    dup_qs = _FakeQS([1, 2])
    monkeypatch.setattr(cms_resources.Accession, "objects", SimpleNamespace(filter=lambda **_k: dup_qs))
    assert resource.dehydrate_has_duplicates(obj) is True


def test_accession_reference_resource_before_import_and_row_paths(monkeypatch):
    resource = cms_resources.AccessionReferenceResource()
    ds = _Dataset(headers=["collection"])
    resource.before_import(ds)
    assert "accession" in ds.headers

    with pytest.raises(ValueError, match="Missing required fields"):
        resource.before_import_row({"collection": "KNM", "specimen_prefix": "ER"})

    monkeypatch.setattr(cms_resources.Accession, "objects", _FakeManager([SimpleNamespace(id=5), SimpleNamespace(id=6)]))
    with pytest.raises(ValueError, match="Multiple Accessions"):
        resource.before_import_row({"collection": "KNM", "specimen_prefix": "ER", "specimen_no": "1"})

    monkeypatch.setattr(cms_resources.Accession, "objects", _FakeManager([]))
    with pytest.raises(ValueError, match="Failed to retrieve"):
        resource.before_import_row({"collection": "KNM", "specimen_prefix": "ER", "specimen_no": "1"})

    monkeypatch.setattr(cms_resources.Accession, "objects", _FakeManager([SimpleNamespace(id=42)]))
    row = {"collection": "KNM", "specimen_prefix": "ER", "specimen_no": "1"}
    resource.before_import_row(row, row_number=2)
    assert row["accession"] == "42"


def test_accession_row_resource_before_import_and_row_paths(monkeypatch):
    resource = cms_resources.AccessionRowResource()
    ds = _Dataset(headers=["collection"])
    resource.before_import(ds)
    assert "accession" in ds.headers and "kari" in ds.headers

    monkeypatch.setattr(cms_resources.Accession, "objects", _FakeManager([SimpleNamespace(id=10)]))
    row = {"collection": "KNM", "specimen_prefix": "ER", "specimen_no": "1", "specimen_suffix": "A"}
    resource.before_import_row(row)
    assert row["accession"] == "10"
    assert row["kari"] == "20"


def test_identification_resource_before_import_row_sets_defaults_and_validates(monkeypatch):
    resource = cms_resources.IdentificationResource()
    ds = _Dataset(headers=[])
    resource.before_import(ds)
    assert "accession_row" in ds.headers

    row = {"collection": "KNM", "specimen_prefix": "ER", "specimen_no": "1", "specimen_suffix": "A"}
    monkeypatch.setattr(cms_resources.AccessionRow, "objects", _FakeManager([SimpleNamespace(id=99)]))
    resource.before_import_row(row)
    assert row["date_identified"] is None
    assert row["accession_row"] == "99"


def test_geological_times_widget_clean_and_render_error_paths():
    widget = cms_resources.GeologicalTimesWidget()
    assert widget.clean(None) == []
    assert widget.clean("") == []
    assert widget.clean("M/Pi") == ["M", "Pi"]

    with pytest.raises(ValueError, match="Invalid geological time value"):
        widget.clean("INVALID")

    rendered = widget.render(["M", "Pi"])
    assert "Miocene" in rendered and "Pliocene" in rendered


def test_place_resource_before_import_row_validation_paths(monkeypatch):
    resource = cms_resources.PlaceResource()

    with pytest.raises(ValueError, match="Invalid relation_type"):
        resource.before_import_row({"relation_type": "bad"}, row_number=1)

    with pytest.raises(ValueError, match="Invalid place_type"):
        resource.before_import_row({"place_type": "bad"}, row_number=2)

    related = SimpleNamespace(locality_id=1, relation_type=cms_resources.PlaceRelation.PART_OF, related_place=None, pk=1)
    monkeypatch.setattr(cms_resources.Place, "objects", SimpleNamespace(get=lambda **_k: related, filter=lambda **_k: _FakeQS([])))
    monkeypatch.setattr(cms_resources.Locality, "objects", SimpleNamespace(get=lambda **_k: SimpleNamespace(id=2)))

    with pytest.raises(ValueError, match="must belong to locality"):
        resource.before_import_row(
            {
                "relation_type": cms_resources.PlaceRelation.PART_OF,
                "related_place": "X",
                "locality": "ER",
                "name": "Target",
            },
            row_number=3,
        )


def test_nature_of_specimen_resource_before_import_row_paths(monkeypatch):
    resource = cms_resources.NatureOfSpecimenResource()
    ds = _Dataset(headers=[])
    resource.before_import(ds)
    assert "accession_row" in ds.headers

    monkeypatch.setattr(cms_resources.AccessionRow, "objects", _FakeManager([SimpleNamespace(id=7)]))
    row = {"collection": "KNM", "specimen_prefix": "ER", "specimen_no": "1", "specimen_suffix": "A"}
    resource.before_import_row(row)
    assert row["accession_row"] == "7"


def test_preparation_resource_before_import_row_and_dehydrate_helpers(monkeypatch):
    resource = cms_resources.PreparationResource()
    ds = _Dataset(headers=[])
    resource.before_import(ds)
    assert "accession_row" in ds.headers

    accession = SimpleNamespace(
        collection=SimpleNamespace(abbreviation="KNM"),
        specimen_prefix=SimpleNamespace(abbreviation="ER"),
        specimen_no=123,
    )
    accession_row = SimpleNamespace(id=55, accession=accession, specimen_suffix="A")

    monkeypatch.setattr(cms_resources.Accession, "objects", _FakeManager([accession]))
    monkeypatch.setattr(cms_resources.AccessionRow, "objects", _FakeManager([accession_row]))

    row = {
        "collection": "KNM",
        "specimen_prefix": "ER",
        "specimen_no": "123",
        "specimen_suffix": "A",
    }
    resource.before_import_row(row)
    assert row["accession_row"] == "55"

    prep_obj = SimpleNamespace(accession_row=accession_row, approval_date=None)
    assert resource.dehydrate_collection(prep_obj) == "KNM"
    assert resource.dehydrate_specimen_prefix(prep_obj) == "ER"
    assert resource.dehydrate_specimen_no(prep_obj) == 123
    assert resource.dehydrate_specimen_suffix(prep_obj) == "A"
    assert resource.dehydrate_approval_date(prep_obj) is None


def test_semicolon_many_to_many_widget_filters_existing_values(monkeypatch):
    widget = cms_resources.SemicolonManyToManyWidget(cms_resources.Locality, field="name", separator=";")

    class _M2MManager:
        @staticmethod
        def filter(**kwargs):
            name = kwargs.get("name")
            if name == "A":
                return _FakeQS([SimpleNamespace(name="A")])
            return _FakeQS([])

    monkeypatch.setattr(cms_resources.Locality, "objects", _M2MManager())
    result = widget.clean("A;B")
    assert len(result) == 1


@pytest.fixture
def current_model_user(db):
    user, _ = get_user_model().objects.get_or_create(username="resource-taxon-user")
    set_current_user(user)
    try:
        yield user
    finally:
        set_current_user(None)


@pytest.mark.django_db
def test_taxon_external_id_widget_uses_source_to_disambiguate_ids(current_model_user):
    now = Taxon.objects.create(
        taxon_name="Now target", taxon_rank="genus", status=TaxonStatus.ACCEPTED,
        external_source="NOW", external_id="shared-id",
    )
    gbif = Taxon.objects.create(
        taxon_name="Gbif target", taxon_rank="genus", status=TaxonStatus.ACCEPTED,
        external_source="GBIF", external_id="shared-id",
    )
    widget = cms_resources.TaxonExternalIdWidget("taxon_source")

    assert widget.clean("shared-id", {"taxon_source": "NOW"}) == now
    assert widget.clean("shared-id", {"taxon_source": "GBIF"}) == gbif
    with pytest.raises(Taxon.MultipleObjectsReturned):
        widget.clean("shared-id", {})


def test_taxonomy_relation_source_columns_export_related_source():
    target = SimpleNamespace(external_source="NOW")
    taxon = SimpleNamespace(accepted_taxon=target, parent=target)
    identification = SimpleNamespace(taxon_record=target)

    taxon_resource = cms_resources.TaxonResource()
    identification_resource = cms_resources.IdentificationResource()
    assert taxon_resource.dehydrate_accepted_taxon_source(taxon) == "NOW"
    assert taxon_resource.dehydrate_parent_source(taxon) == "NOW"
    assert identification_resource.dehydrate_taxon_record_source(identification) == "NOW"
    assert "accepted_taxon_source" in taxon_resource._meta.fields
    assert "parent_source" in taxon_resource._meta.fields
    assert "taxon_record_source" in identification_resource._meta.fields
    assert identification_resource._meta.export_order[
        identification_resource._meta.export_order.index("taxon_record") + 1
    ] == "taxon_record_source"
