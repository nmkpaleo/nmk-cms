from __future__ import annotations

from types import SimpleNamespace

import pytest

from cms import resources as cms_resources


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
