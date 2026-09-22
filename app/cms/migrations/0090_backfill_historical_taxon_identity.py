"""Populate identities for history written before taxonomy unification."""
from django.db import migrations


def backfill_history_identity(apps, schema_editor):
    History = apps.get_model("cms", "HistoricalTaxon")
    rows = History.objects.using(schema_editor.connection.alias)
    while True:
        batch = list(rows.filter(identity_key="").order_by("pk")[:1000])
        if not batch:
            break
        for row in batch:
            rank = " ".join((row.taxon_rank or "").split()).lower() or "species"
            name = " ".join((row.taxon_name or "").split()).lower()
            row.identity_key = rank + ":" + name
        rows.bulk_update(batch, ["identity_key"], batch_size=1000)


class Migration(migrations.Migration):
    dependencies = [("cms", "0089_alter_historicaltaxon_author_year_and_more")]
    operations = [migrations.RunPython(backfill_history_identity, migrations.RunPython.noop)]
