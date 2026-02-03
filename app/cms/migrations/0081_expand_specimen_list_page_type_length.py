from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0080_update_specimen_list_page_types"),
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
    ]
