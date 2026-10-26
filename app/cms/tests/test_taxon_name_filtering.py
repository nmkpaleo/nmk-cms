"""Skipping names GBIF/NOW cannot match, and extracting identification qualifiers."""
import pytest
from django.test import override_settings

from app.cms.models import Identification, Taxon
from app.cms.taxon_identity import merge_qualifier, parse_taxon_label
from app.cms.taxonomy.snapshot import (
    _deserialize_preview, _serialize_preview, apply_signed_preview, catalogue_fingerprint, sign_preview,
)
from app.cms.tests.test_sync_gbif import payload, service
from app.cms.tests.test_sync_now import _field_slip, _identification, authenticated_model_user  # noqa: F401
from django.contrib.auth import get_user_model

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("label", [
    "Canis lupus", "Equus", "canis LUPUS", "Canis lupus familiaris", "Müller-ia bär", "Canis lupus subsp. familiaris",
])
def test_parser_accepts_valid_names(label):
    assert parse_taxon_label(label).valid


@pytest.mark.parametrize("label,reason", [
    ("Canis lupus 2", "numbers"),
    ("Canis (lupus)", "special characters"),
    ("Canis lupus, 1758", "numbers"),
    ("Canis lupus familiaris dingo extra", "more than 3 words"),
    ("Canis/Vulpes", "special characters"),
    ("unknown", "placeholder"),
    ("", "empty"),
    ("indet.", "empty"),
])
def test_parser_rejects_unmatchable_names(label, reason):
    parsed = parse_taxon_label(label)
    assert not parsed.valid
    assert reason in parsed.reason


@pytest.mark.parametrize("label,name,qualifiers", [
    ("Canis cf. lupus", "Canis lupus", ("cf.",)),
    ("Canis aff. lupus", "Canis lupus", ("aff.",)),
    ("Felis sp.", "Felis", ("sp.",)),
    ("Aves indet", "Aves", ("indet.",)),
    ("Canis sp. nov.", "Canis", ("sp. nov.",)),
    ("Canis lupus?", "Canis lupus", ("?",)),
    ("Canis lupus subsp. familiaris", "Canis lupus familiaris", ()),
    ("Papionini Indet indet", "Papionini", ("indet.",)),
    ("Canis cf. lupus cf.", "Canis lupus", ("cf.",)),
])
def test_parser_strips_qualifiers_and_rank_markers(label, name, qualifiers):
    parsed = parse_taxon_label(label)
    assert parsed.valid
    assert (parsed.name, parsed.qualifiers) == (name, qualifiers)


def test_merge_qualifier_appends_without_duplicates():
    assert merge_qualifier(None, ["cf."]) == "cf."
    assert merge_qualifier("aff.", ["cf."]) == "aff. cf."
    assert merge_qualifier("CF.", ["cf."]) == "CF."
    assert merge_qualifier("spp.", ["sp."]) == "spp. sp."


class _RecordingGbif:
    def __init__(self, svc):
        self.names = []
        original = svc.gbif.match_many
        svc.gbif.match_many = lambda names: (self.names.extend(names), original(names))[1]


@override_settings(TAXON_NOW_ACCEPTED_URL="accepted", TAXON_NOW_SYNONYMS_URL="synonyms")
def test_preview_skips_unmatchable_names_and_queries_cleaned_ones():
    for name in ("Struthio cf. camelus", "Bad name 12", "One two three four", "Canis (x)"):
        _identification(name)
    _field_slip("Field only")
    svc = service(payload("Struthio camelus", rank="SPECIES"))
    recorder = _RecordingGbif(svc)

    preview = svc.preview()

    queried = {name for name, _rank in recorder.names}
    assert queried == {"struthio camelus"}
    skipped = {s.name: s.reason for s in preview.skipped_names}
    assert set(skipped) == {"Bad name 12", "One two three four", "Canis (x)"}
    assert preview.counts["skipped_invalid_names"] == 3
    assert [u.additions for u in preview.qualifier_updates] == [["cf."]]


@override_settings(TAXON_NOW_ACCEPTED_URL="accepted", TAXON_NOW_SYNONYMS_URL="synonyms")
def test_qualifier_is_written_on_apply_only_and_not_duplicated():
    with_qualifier = _identification("Struthio cf. camelus")
    existing = _identification("Struthio aff. camelus")
    Identification.objects.filter(pk=existing.pk).update(identification_qualifier="aff.")
    already = _identification("Struthio cf. camelus")
    Identification.objects.filter(pk=already.pk).update(identification_qualifier="CF.")
    svc = service(payload("Struthio camelus", rank="SPECIES"))
    person = get_user_model().objects.get(username="sync-now-user")

    preview = svc.preview()
    # Only current identifications are considered; each is on its own row here.
    assert {q.identification_id for q in preview.qualifier_updates} == {with_qualifier.pk}
    with_qualifier.refresh_from_db()
    assert not with_qualifier.identification_qualifier

    data = _serialize_preview(preview)
    restored = _deserialize_preview(data, {})
    assert restored.qualifier_updates == preview.qualifier_updates
    assert restored.skipped_names == preview.skipped_names

    token = sign_preview(preview, person.pk, catalogue_fingerprint())
    result = apply_signed_preview(token, person.pk, svc)

    with_qualifier.refresh_from_db()
    assert with_qualifier.identification_qualifier == "cf."
    assert with_qualifier.taxon_verbatim == "Struthio cf. camelus"
    assert with_qualifier.history.count() >= 2
    assert result.preview.counts["qualifiers_added"] == 1
    assert Taxon.objects.filter(taxon_name="Struthio camelus").exists()
    linked = Identification.objects.get(pk=with_qualifier.pk)
    assert linked.taxon_record is not None


@override_settings(TAXON_NOW_ACCEPTED_URL="accepted", TAXON_NOW_SYNONYMS_URL="synonyms")
def test_field_slip_names_are_not_a_sync_source():
    _field_slip("Struthio")
    svc = service(payload())
    recorder = _RecordingGbif(svc)
    assert svc.preview().counts["created"] == 0
    assert recorder.names == []


@override_settings(TAXON_NOW_ACCEPTED_URL="accepted", TAXON_NOW_SYNONYMS_URL="synonyms")
def test_preview_for_name_rejects_unmatchable_name():
    with pytest.raises(ValueError, match="cannot be synced"):
        service(payload()).preview_for_name("Struthio 2")


@override_settings(TAXON_NOW_ACCEPTED_URL="accepted", TAXON_NOW_SYNONYMS_URL="synonyms")
def test_skipped_names_and_qualifiers_render_in_admin_template():
    from django.template.loader import render_to_string
    from cms.admin import _serialize_preview_for_template

    _identification("Struthio cf. camelus")
    _identification("Bad name 12")
    preview = service(payload("Struthio camelus", rank="SPECIES")).preview()

    html = render_to_string(
        "admin/taxonomy/_skipped_names.html", {"preview_data": _serialize_preview_for_template(preview)}
    )

    assert "Bad name 12" in html
    assert "contains numbers" in html
    assert "Struthio cf. camelus" in html
