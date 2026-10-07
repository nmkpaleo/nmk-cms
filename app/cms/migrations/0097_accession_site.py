from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0096_historicalaccession_merge_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="accession",
            name="site",
            field=models.ForeignKey(
                blank=True,
                help_text="Site or collecting area for this collecting event.",
                limit_choices_to={"place_type__in": ["Site", "CollectingArea"]},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="accessions",
                to="cms.place",
            ),
        ),
        migrations.AddField(
            model_name="historicalaccession",
            name="site",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="Site or collecting area for this collecting event.",
                limit_choices_to={"place_type__in": ["Site", "CollectingArea"]},
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="cms.place",
            ),
        ),
    ]
