from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0098_media_report_indexes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="historicalreference",
            name="year",
            field=models.CharField(
                blank=True,
                help_text="Publication year (YYYY).",
                max_length=4,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="reference",
            name="year",
            field=models.CharField(
                blank=True,
                help_text="Publication year (YYYY).",
                max_length=4,
                null=True,
            ),
        ),
    ]
