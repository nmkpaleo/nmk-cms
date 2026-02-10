from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0084_fieldslip_comment"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalfieldslip",
            name="comment",
            field=models.TextField(
                blank=True,
                help_text="Additional notes from review.",
                null=True,
            ),
        ),
    ]
