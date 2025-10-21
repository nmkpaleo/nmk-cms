import pytest
from django.test import override_settings

from app.cms.models import Taxon, TaxonExternalSource, TaxonStatus, TaxonomyImport
from app.cms.taxonomy.sync import NowTaxonomySyncService


class _StaticResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.status_code = 200
        self.encoding = None

    def raise_for_status(self) -> None:  # pragma: no cover - simple placeholder
        return None


def _http_get_factory(mapping):
    def _http_get(url: str):
        try:
            text = mapping[url]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AssertionError(f"Unexpected URL requested: {url}") from exc
        return _StaticResponse(text)

    return _http_get


@pytest.mark.django_db
@override_settings(
    TAXON_NOW_ACCEPTED_URL="https://example.com/accepted.tsv",
    TAXON_NOW_SYNONYMS_URL="https://example.com/synonyms.tsv",
    TAXON_SYNC_DEACTIVATE_MISSING=True,
)
def test_now_sync_creates_updates_and_deactivates(db):
    accepted_existing = Taxon.objects.create(
        external_source=TaxonExternalSource.NOW,
        external_id="NOW:species:Herpestes major",
        author_year="Old Author",
        status=TaxonStatus.ACCEPTED,
        is_active=False,
        source_version="old",
        taxon_rank="species",
        taxon_name="Herpestes major",
        kingdom="Animalia",
        phylum="Chordata",
        class_name="Mammalia",
        order="Old order",
        superfamily="",
        family="Outdated Family",
        subfamily="",
        tribe="",
        genus="OldGenus",
        species="major",
    )
    synonym_existing = Taxon.objects.create(
        external_source=TaxonExternalSource.NOW,
        external_id="NOW:syn:Herpestes majorus::accepted:Herpestes major",
        author_year="Old Syn Author",
        status=TaxonStatus.SYNONYM,
        accepted_taxon=accepted_existing,
        is_active=False,
        source_version="old",
        taxon_rank="species",
        taxon_name="Herpestes majorus",
        kingdom="Animalia",
        phylum="Chordata",
        class_name="Mammalia",
        order="Old order",
        superfamily="",
        family="Outdated Family",
        subfamily="",
        tribe="",
        genus="OldGenus",
        species="majorus",
    )
    to_deactivate = Taxon.objects.create(
        external_source=TaxonExternalSource.NOW,
        external_id="NOW:species:Obsolete taxon",
        author_year="Removed",
        status=TaxonStatus.ACCEPTED,
        is_active=True,
        source_version="old",
        taxon_rank="species",
        taxon_name="Obsolete taxon",
        kingdom="Animalia",
        phylum="Chordata",
        class_name="Mammalia",
        order="Carnivora",
        family="Herpestidae",
        genus="Obsolete",
        species="taxon",
    )

    accepted_tsv = "\n".join(
        [
            "taxon_name\ttaxon_rank\torder_name\tsuperfamily\tfamily\tsubfamily\ttribe\tgenus\tspecies\tauthor\tSTG_TIME_STAMP",
            "Herpestes major\tspecies\tCarnivora\tHerpestoidea\tHerpestidae\tHerpestinae\t\tHerpestes\tmajor\tNew Author\t2024-01-01",
            "Newcanis novus\tspecies\tCarnivora\tCanidoidea\tCanidae\tCaninae\tCanini\tNewcanis\tnovus\tA. Researcher\t2024-01-01",
        ]
    )
    synonyms_tsv = "\n".join(
        [
            "syn_name\ttaxon_name\ttaxon_rank\torder_name\tsuperfamily\tfamily\tsubfamily\ttribe\tgenus\tspecies\tauthor\tSTG_TIME_STAMP",
            "Herpestes majorus\tHerpestes major\tspecies\tCarnivora\tHerpestoidea\tHerpestidae\tHerpestinae\t\tHerpestes\tmajorus\tUpdated Syn Author\t2024-01-01",
            "Newcanis junior\tNewcanis novus\tspecies\tCarnivora\tCanidoidea\tCanidae\tCaninae\tCanini\tNewcanis\tjunior\tB. Res\t2024-01-01",
        ]
    )

    http_get = _http_get_factory(
        {
            "https://example.com/accepted.tsv": accepted_tsv,
            "https://example.com/synonyms.tsv": synonyms_tsv,
        }
    )

    service = NowTaxonomySyncService(http_get=http_get)

    preview = service.preview()
    assert preview.counts == {
        "created": 2,
        "updated": 2,
        "deactivated": 1,
        "synonym_links": 2,
        "issues": 0,
    }
    assert len(preview.accepted_to_create) == 1
    assert len(preview.synonyms_to_create) == 1

    result = service.sync(apply=True)
    assert result.import_log is not None
    result.import_log.refresh_from_db()
    assert result.import_log.counts["created"] == 2
    assert result.import_log.counts["updated"] == 2
    assert result.import_log.counts["deactivated"] == 1
    assert TaxonomyImport.objects.count() == 1

    accepted_existing.refresh_from_db()
    assert accepted_existing.author_year == "New Author"
    assert accepted_existing.is_active is True
    assert accepted_existing.source_version == "2024-01-01"
    assert accepted_existing.order == "Carnivora"
    assert accepted_existing.superfamily == "Herpestoidea"
    assert accepted_existing.family == "Herpestidae"
    assert accepted_existing.subfamily == "Herpestinae"
    assert accepted_existing.genus == "Herpestes"
    assert accepted_existing.species == "major"

    synonym_existing.refresh_from_db()
    assert synonym_existing.author_year == "Updated Syn Author"
    assert synonym_existing.is_active is True
    assert synonym_existing.accepted_taxon == accepted_existing
    assert synonym_existing.order == "Carnivora"
    assert synonym_existing.family == "Herpestidae"
    assert synonym_existing.genus == "Herpestes"

    created_synonym = Taxon.objects.get(external_id="NOW:syn:Newcanis junior::accepted:Newcanis novus")
    created_accepted = Taxon.objects.get(external_id="NOW:species:Newcanis novus")
    assert created_synonym.accepted_taxon == created_accepted
    assert created_accepted.order == "Carnivora"
    assert created_accepted.superfamily == "Canidoidea"
    assert created_accepted.family == "Canidae"
    assert created_accepted.subfamily == "Caninae"
    assert created_accepted.tribe == "Canini"
    assert created_accepted.genus == "Newcanis"
    assert created_accepted.species == "novus"

    to_deactivate.refresh_from_db()
    assert to_deactivate.is_active is False

    post_preview = service.preview()
    assert post_preview.counts == {
        "created": 0,
        "updated": 0,
        "deactivated": 0,
        "synonym_links": 0,
        "issues": 0,
    }


@pytest.mark.django_db
@override_settings(
    TAXON_NOW_ACCEPTED_URL="https://example.com/accepted.tsv",
    TAXON_NOW_SYNONYMS_URL="https://example.com/synonyms.tsv",
    TAXON_SYNC_DEACTIVATE_MISSING=True,
)
def test_now_sync_skips_subranks_and_limits_lower_taxonomy(db):
    accepted_tsv = "\n".join(
        [
            "taxon_name\ttaxon_rank\torder_name\tsuperfamily\tfamily\tsubfamily\ttribe\tgenus\tspecies\tauthor\tSTG_TIME_STAMP",
            "Theria\tsubclass\tTheria\t\t\t\t\t\t\tA. Person\t2024-02-01",
            "Felidae\tfamily\tCarnivora\tFeliformia\tFelidae\t\t\t\t\tB. Person\t2024-02-01",
        ]
    )
    synonyms_tsv = "\n".join(
        [
            "syn_name\ttaxon_name\ttaxon_rank\torder_name\tsuperfamily\tfamily\tsubfamily\ttribe\tgenus\tspecies\tauthor\tSTG_TIME_STAMP",
        ]
    )

    http_get = _http_get_factory(
        {
            "https://example.com/accepted.tsv": accepted_tsv,
            "https://example.com/synonyms.tsv": synonyms_tsv,
        }
    )

    service = NowTaxonomySyncService(http_get=http_get)
    preview = service.preview()

    assert len(preview.accepted_to_create) == 1
    family_record = preview.accepted_to_create[0]
    assert family_record.name == "Felidae"
    assert family_record.rank == "family"
    assert family_record.taxonomy["order"] == "Carnivora"
    assert family_record.taxonomy["superfamily"] == "Feliformia"
    assert family_record.taxonomy["family"] == "Felidae"
    assert family_record.taxonomy["genus"] == ""
    assert family_record.taxonomy["species"] == ""


@pytest.mark.django_db
@override_settings(
    TAXON_NOW_ACCEPTED_URL="https://example.com/accepted.tsv",
    TAXON_NOW_SYNONYMS_URL="https://example.com/synonyms.tsv",
    TAXON_SYNC_DEACTIVATE_MISSING=True,
)
def test_now_sync_records_issue_when_missing_accepted(db):
    accepted_tsv = "\n".join(
        [
            "taxon_name\ttaxon_rank\tauthor\tSTG_TIME_STAMP",
            "Alpha beta\tspecies\tAuthor\t2024-01-01",
        ]
    )
    synonyms_tsv = "\n".join(
        [
            "syn_name\ttaxon_name\ttaxon_rank\tauthor\tSTG_TIME_STAMP",
            "Missing target\tGhost species\tspecies\tSomeone\t2024-01-01",
        ]
    )
    http_get = _http_get_factory(
        {
            "https://example.com/accepted.tsv": accepted_tsv,
            "https://example.com/synonyms.tsv": synonyms_tsv,
        }
    )

    service = NowTaxonomySyncService(http_get=http_get)
    preview = service.preview()

    assert preview.counts["issues"] == 1
    assert preview.synonyms_to_create == []
    assert preview.synonyms_to_update == []
    assert preview.issues[0].code == "missing-accepted"
