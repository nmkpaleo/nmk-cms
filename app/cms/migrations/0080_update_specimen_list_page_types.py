from django.db import migrations, models


def migrate_page_types(apps, schema_editor):
    SpecimenListPage = apps.get_model("cms", "SpecimenListPage")
    SpecimenListPage.objects.filter(page_type="specimen_list").update(
        page_type="specimen_list_details"
    )

    HistoricalSpecimenListPage = apps.get_model("cms", "HistoricalSpecimenListPage")
    HistoricalSpecimenListPage.objects.filter(page_type="specimen_list").update(
        page_type="specimen_list_details"
    )


def reverse_page_types(apps, schema_editor):
    SpecimenListPage = apps.get_model("cms", "SpecimenListPage")
    SpecimenListPage.objects.filter(page_type="specimen_list_details").update(
        page_type="specimen_list"
    )

    HistoricalSpecimenListPage = apps.get_model("cms", "HistoricalSpecimenListPage")
    HistoricalSpecimenListPage.objects.filter(page_type="specimen_list_details").update(
        page_type="specimen_list"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0079_specimenlistpage_classification"),
    ]

    operations = [
        migrations.AlterField(
            model_name="historicalspecimenlistpage",
            name="page_type",
            field=models.CharField(
                choices=[
                    ("unknown", "Unknown"),
                    ("specimen_list_details", "Specimen list (accession details)"),
                    ("specimen_list_relations", "Specimen list (accession/field relations)"),
                    ("free_text", "Free text"),
                    ("typed_text", "Typed text"),
                    ("other", "Other"),
                ],
                default="unknown",
                help_text="Classified page type.",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="specimenlistpage",
            name="page_type",
            field=models.CharField(
                choices=[
                    ("unknown", "Unknown"),
                    ("specimen_list_details", "Specimen list (accession details)"),
                    ("specimen_list_relations", "Specimen list (accession/field relations)"),
                    ("free_text", "Free text"),
                    ("typed_text", "Typed text"),
                    ("other", "Other"),
                ],
                default="unknown",
                help_text="Classified page type.",
                max_length=30,
            ),
        ),
        migrations.RunPython(migrate_page_types, reverse_page_types),
    ]
