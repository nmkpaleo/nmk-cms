from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("cms", "0094_create_researchers_group")]

    operations = [
        migrations.AddField(
            model_name="accession",
            name="merged_into",
            field=models.ForeignKey(
                blank=True,
                help_text="Canonical accession retained after this accession was merged.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="merged_accessions",
                to="cms.accession",
            ),
        ),
        migrations.AddField(
            model_name="accession",
            name="merged_on",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="accession",
            name="merged_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="accessions_merged",
                to="auth.user",
            ),
        ),
        migrations.AlterModelOptions(
            name="accession",
            options={
                "ordering": ["collection", "specimen_prefix", "specimen_no"],
                "permissions": [("can_merge", "Can merge accession records")],
                "verbose_name": "Accession",
                "verbose_name_plural": "Accessions",
            },
        ),
    ]
