"""Exercise deduplication with the real pre-constraint database schema."""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_taxon_identity_migration_preserves_links_and_resolves_ambiguity():
    before = [("cms", "0087_collectionmethod_fossilgroup_grainsize_and_more")]
    after = [("cms", "0088_remove_taxon_unique_taxon_rank_name_authorship_and_more")]
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    try:
        apps = executor.loader.project_state(before).apps
        Taxon = apps.get_model("cms", "Taxon")
        Collection = apps.get_model("cms", "Collection")
        Locality = apps.get_model("cms", "Locality")
        Accession = apps.get_model("cms", "Accession")
        AccessionRow = apps.get_model("cms", "AccessionRow")
        Identification = apps.get_model("cms", "Identification")
        History = apps.get_model("cms", "HistoricalIdentification")
        Drawer = apps.get_model("cms", "DrawerRegister")
        legacy = Taxon.objects.create(taxon_name="  Panthera  ", taxon_rank="GENUS", external_source="LEGACY")
        now = Taxon.objects.create(taxon_name="Panthera", taxon_rank="genus", external_source="NOW", external_id="NOW:genus:Panthera", class_name="Mammalia")
        child = Taxon.objects.create(taxon_name="Leo", taxon_rank="genus", status="synonym", accepted_taxon=legacy, parent=legacy)
        collection = Collection.objects.create(abbreviation="MG", description="Migration")
        locality = Locality.objects.create(abbreviation="ML", name="Migration")
        accession = Accession.objects.create(collection=collection, specimen_prefix=locality, specimen_no=1)
        row = AccessionRow.objects.create(accession=accession)
        linked = Identification.objects.create(accession_row=row, taxon_verbatim="Panthera", taxon_record=legacy)
        unlinked = Identification.objects.create(accession_row=row, taxon_verbatim="Panthera")
        history = History.objects.create(id=linked.pk, accession_row_id=row.pk, taxon_verbatim="Panthera",
                                         taxon_record_id=legacy.pk, history_date=timezone.now(), history_type="+",
                                         created_on=timezone.now(), modified_on=timezone.now())
        drawer = Drawer.objects.create(code="MG", description="Migration", estimated_documents=1)
        drawer.taxa.add(legacy, now)
        executor = MigrationExecutor(connection)
        executor.migrate(after)
        apps = executor.loader.project_state(after).apps
        Taxon = apps.get_model("cms", "Taxon")
        Identification = apps.get_model("cms", "Identification")
        assert not Taxon.objects.filter(pk=legacy.pk).exists()
        assert Taxon.objects.get(pk=now.pk).identity_key == "genus:panthera"
        assert Identification.objects.get(pk=linked.pk).taxon_record_id == now.pk
        assert Identification.objects.get(pk=unlinked.pk).taxon_record_id == now.pk
        assert apps.get_model("cms", "HistoricalIdentification").objects.get(history_id=history.history_id).taxon_record_id == now.pk
        assert list(apps.get_model("cms", "DrawerRegister").objects.get(pk=drawer.pk).taxa.values_list("pk", flat=True)) == [now.pk]
        assert Taxon.objects.get(pk=child.pk).accepted_taxon_id == now.pk
        assert Taxon.objects.get(pk=child.pk).parent_id == now.pk
    finally:
        MigrationExecutor(connection).migrate(after)
