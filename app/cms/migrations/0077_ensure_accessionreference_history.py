from django.db import migrations


def ensure_accession_reference_history(apps, schema_editor):
    historical_model = apps.get_model("cms", "HistoricalAccessionReference")
    table_name = historical_model._meta.db_table

    existing_tables = set(schema_editor.connection.introspection.table_names())
    if table_name in existing_tables:
        return

    schema_editor.create_model(historical_model)


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0076_alter_accession_unique_together_and_more"),
    ]

    operations = [
        migrations.RunPython(
            ensure_accession_reference_history, migrations.RunPython.noop
        ),
    ]
