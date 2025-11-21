from django.db import migrations


TAXON_CHUNK_SIZE = 500


def build_taxon_name_map(Taxon):
    """Map normalized taxon_name -> unique Taxon.id. Ambiguous names map to None."""
    name_map = {}
    for taxon_id, taxon_name in Taxon.objects.exclude(
        taxon_name__isnull=True
    ).exclude(taxon_name__exact="").values_list("id", "taxon_name"):
        normalized = taxon_name.strip().casefold()
        if not normalized:
            continue
        if normalized in name_map:
            name_map[normalized] = None
        else:
            name_map[normalized] = taxon_id
    return name_map


def populate_taxon_fields(apps, schema_editor):
    Identification = apps.get_model("cms", "Identification")
    HistoricalIdentification = apps.get_model("cms", "HistoricalIdentification")
    Taxon = apps.get_model("cms", "Taxon")

    name_map = build_taxon_name_map(Taxon)

    def _populate(model):
        qs = model.objects.select_related("taxon_record")
        for obj in qs.iterator(chunk_size=TAXON_CHUNK_SIZE):
            updates = {}
            taxon_text = (obj.taxon or "").strip()
            verbatim = (obj.taxon_verbatim or "").strip()

            if not verbatim:
                if taxon_text:
                    updates["taxon_verbatim"] = taxon_text
                elif obj.taxon_record and obj.taxon_record.taxon_name:
                    updates["taxon_verbatim"] = obj.taxon_record.taxon_name

            if not obj.taxon_record_id and taxon_text:
                normalized = taxon_text.casefold()
                taxon_id = name_map.get(normalized)
                if taxon_id:
                    updates["taxon_record_id"] = taxon_id

            if updates:
                model.objects.filter(pk=obj.pk).update(**updates)

    for model in (Identification, HistoricalIdentification):
        _populate(model)


def restore_legacy_taxon(apps, schema_editor):
    Identification = apps.get_model("cms", "Identification")
    HistoricalIdentification = apps.get_model("cms", "HistoricalIdentification")

    def _restore(model):
        qs = model.objects.all()
        for obj in qs.iterator(chunk_size=TAXON_CHUNK_SIZE):
            taxon_text = (obj.taxon or "").strip()
            if not taxon_text and obj.taxon_verbatim:
                model.objects.filter(pk=obj.pk).update(taxon=obj.taxon_verbatim)

    for model in (Identification, HistoricalIdentification):
        _restore(model)


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0069_historicalidentification_taxon_verbatim_and_more"),
    ]

    operations = [
        migrations.RunPython(populate_taxon_fields, reverse_code=restore_legacy_taxon),
    ]
