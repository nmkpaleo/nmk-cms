from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cms", "0042_accessionrow_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="UnexpectedSpecimen",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_on", models.DateTimeField(auto_now_add=True, verbose_name="Date Created")),
                ("modified_on", models.DateTimeField(auto_now=True, verbose_name="Date Modified")),
                ("identifier", models.CharField(max_length=255)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="cms_unexpectedspecimen_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Created by",
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="cms_unexpectedspecimen_modified",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Modified by",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_on"],
                "verbose_name": "Unexpected Specimen",
                "verbose_name_plural": "Unexpected Specimens",
            },
        ),
    ]

