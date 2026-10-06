from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0095_accession_merge_state"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalaccession",
            name="merged_by",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="historicalaccession",
            name="merged_into",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="Canonical accession retained after this accession was merged.",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="cms.accession",
            ),
        ),
        migrations.AddField(
            model_name="historicalaccession",
            name="merged_on",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
