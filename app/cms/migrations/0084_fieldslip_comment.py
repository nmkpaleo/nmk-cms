from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0083_add_review_status_specimen_list_page"),
    ]

    operations = [
        migrations.AddField(
            model_name="fieldslip",
            name="comment",
            field=models.TextField(
                blank=True,
                help_text="Additional notes from review.",
                null=True,
            ),
        ),
    ]
