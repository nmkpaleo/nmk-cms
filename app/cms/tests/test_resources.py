import pytest

from app.cms.models import Storage
from app.cms.resources import GeologicalTimesWidget, StorageResource


@pytest.mark.django_db
def test_storage_resource_exports_and_imports_parent_area_name():
    parent = Storage.objects.create(area="Main Room")
    child = Storage.objects.create(area="Cabinet 1", parent_area=parent)
    resource = StorageResource()

    exported = resource.export(Storage.objects.filter(pk=child.pk))
    assert exported.dict[0]["parent_area"] == "Main Room"

    Storage.objects.filter(pk=child.pk).delete()
    resource.import_data(exported, dry_run=False)

    imported = Storage.objects.get(area="Cabinet 1")
    assert imported.parent_area == parent


@pytest.mark.parametrize(
    "value,expected",
    [
        ([], ""),
        (["M"], "Miocene"),
        (["M", "H"], "Miocene/Holocene"),
    ],
)
def test_geological_times_widget_render_accepts_kwargs(value, expected):
    widget = GeologicalTimesWidget()
    assert widget.render(value, export_fields=None) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("M/Pi", ["M", "Pi"]),
        ("Miocene/Pliocene", ["M", "Pi"]),
        ("Miocene/ Pi", ["M", "Pi"]),
    ],
)
def test_geological_times_widget_clean_accepts_labels_and_codes(value, expected):
    widget = GeologicalTimesWidget()
    assert widget.clean(value) == expected
