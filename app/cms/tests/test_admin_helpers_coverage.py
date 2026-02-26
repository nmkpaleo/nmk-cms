from types import SimpleNamespace

from cms.admin import (
    _serialize_changeset,
    _serialize_preview_for_template,
    _sync_permission_codename,
    _user_can_sync_taxa,
)


class _User:
    def __init__(self, active, allowed):
        self.is_active = active
        self._allowed = allowed

    def has_perm(self, codename):
        return self._allowed and codename.endswith(".can_sync")


def test_sync_permission_codename_and_access_check():
    code = _sync_permission_codename()
    assert code.endswith(".can_sync")
    assert _user_can_sync_taxa(_User(True, True)) is True
    assert _user_can_sync_taxa(_User(False, True)) is False
    assert _user_can_sync_taxa(None) is False


def test_serialize_changeset_handles_regular_and_accepted_taxon_fields():
    accepted_taxon = SimpleNamespace(taxon_name="Old Taxon")
    instance = SimpleNamespace(name="Existing", accepted_taxon=accepted_taxon)
    record = SimpleNamespace(accepted_name="New Accepted")
    update = SimpleNamespace(instance=instance, record=record, changes={"name": "New", "accepted_taxon": "ignored"})

    serialized = _serialize_changeset(update)
    assert serialized[0]["label"] == "Name"
    assert serialized[0]["old"] == "Existing"
    assert serialized[0]["new"] == "New"
    assert serialized[1]["label"] == "Accepted Taxon"
    assert serialized[1]["old"] == "Old Taxon"
    assert serialized[1]["new"] == "New Accepted"


def test_serialize_preview_for_template_shapes_all_sections():
    update = SimpleNamespace(
        record=SimpleNamespace(name="Syn", accepted_name="Acc", external_id="ext-2"),
        instance=SimpleNamespace(accepted_taxon=None),
        changes={"accepted_taxon": "x"},
    )
    preview = SimpleNamespace(
        accepted_to_create=[SimpleNamespace(name="A", rank="species", author_year="1900", external_id="ext-1")],
        accepted_to_update=[update],
        synonyms_to_create=[SimpleNamespace(name="S", accepted_name="A", external_id="ext-3")],
        synonyms_to_update=[update],
        to_deactivate=[SimpleNamespace(taxon_name="D", external_id="ext-4")],
        issues=[SimpleNamespace(code="warn", message="msg", context={"k": "v"})],
    )

    payload = _serialize_preview_for_template(preview)
    assert payload["accepted_creates"][0]["name"] == "A"
    assert payload["accepted_updates"][0]["changes"][0]["label"] == "Accepted Taxon"
    assert payload["synonym_creates"][0]["accepted_name"] == "A"
    assert payload["deactivations"][0]["name"] == "D"
    assert payload["issues"][0]["code"] == "warn"
