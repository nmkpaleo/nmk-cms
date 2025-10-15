from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0063_mergelog"),
    ]

    operations = [
        migrations.AddField(
            model_name="mergelog",
            name="relation_actions",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Actions executed against related objects during the merge.",
            ),
        ),
    ]
