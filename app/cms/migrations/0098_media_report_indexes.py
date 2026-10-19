from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0097_accession_site"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="media",
            index=models.Index(fields=["ocr_status"], name="media_ocr_status_idx"),
        ),
        migrations.AddIndex(
            model_name="media",
            index=models.Index(fields=["created_on"], name="media_created_on_idx"),
        ),
        migrations.AddIndex(
            model_name="media",
            index=models.Index(fields=["created_on", "ocr_status"], name="media_created_ocr_idx"),
        ),
    ]
