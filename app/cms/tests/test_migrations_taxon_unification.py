import pytest
from crum import set_current_user
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


pytestmark = pytest.mark.django_db


def _create_taxon(apps, name: str, *, is_active: bool = True):
    Taxon = apps.get_model("cms", "Taxon")
    parts = name.split()
    genus = parts[0]
    species = parts[1] if len(parts) > 1 else parts[0]
    return Taxon.objects.create(
        external_source="NOW",
        external_id=f"NOW:{name}",
        author_year="Author 1900",
        status="accepted",
        accepted_taxon=None,
        parent=None,
        is_active=is_active,
        source_version="v1",
        taxon_rank="species",
        taxon_name=name,
        kingdom="Animalia",
        phylum="Chordata",
        class_name="Mammalia",
        order="Orderus",
        superfamily="",
        family="Familia",
        subfamily="",
        tribe="",
        genus=genus,
        species=species,
        infraspecific_epithet="",
        scientific_name_authorship="Author",
    )


def test_taxon_unification_migration_backfills_and_links_unique_matches():
    executor = MigrationExecutor(connection)
    migrate_from = [("cms", "0068_historicallocality_geological_times_and_more")]
    migrate_to = [("cms", "0071_alter_historicalidentification_taxon_verbatim_and_more")]

    executor.migrate(migrate_from)
    old_apps = executor.loader.project_state(migrate_from).apps

    User = get_user_model()
    user = User.objects.create(username="migration-user")
    set_current_user(user)

    Collection = old_apps.get_model("cms", "Collection")
    Locality = old_apps.get_model("cms", "Locality")
    Accession = old_apps.get_model("cms", "Accession")
    AccessionRow = old_apps.get_model("cms", "AccessionRow")
    Identification = old_apps.get_model("cms", "Identification")

    collection = Collection.objects.create(abbreviation="TC", description="Test Collection")
    locality = Locality.objects.create(abbreviation="TL", name="Test Locality")
    accession = Accession.objects.create(
        collection=collection,
        specimen_prefix=locality,
        specimen_no=1,
    )
    accession_row = AccessionRow.objects.create(accession=accession)

    matched_taxon = _create_taxon(old_apps, "Linkedus example")
    _create_taxon(old_apps, "Ambiguous taxon")
    _create_taxon(old_apps, "Ambiguous taxon")

    linked_ident = Identification.objects.create(
        accession_row=accession_row,
        taxon="Linkedus example",
    )
    ambiguous_ident = Identification.objects.create(
        accession_row=accession_row,
        taxon="Ambiguous taxon",
    )

    set_current_user(None)

    executor.migrate(migrate_to)
    new_apps = executor.loader.project_state(migrate_to).apps
    NewIdentification = new_apps.get_model("cms", "Identification")

    linked = NewIdentification.objects.get(pk=linked_ident.pk)
    assert linked.taxon_verbatim == "Linkedus example"
    assert linked.taxon_record_id == matched_taxon.id

    ambiguous = NewIdentification.objects.get(pk=ambiguous_ident.pk)
    assert ambiguous.taxon_verbatim == "Ambiguous taxon"
    assert ambiguous.taxon_record_id is None

