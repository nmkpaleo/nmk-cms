from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import simple_history.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cms", "0065_taxon_schema_update"),
    ]

    operations = [
        migrations.CreateModel(
            name="HistoricalTaxonomyImport",
            fields=[
                (
                    "id",
                    models.BigIntegerField(
                        auto_created=True,
                        blank=True,
                        db_index=True,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_on",
                    models.DateTimeField(
                        blank=True,
                        editable=False,
                        help_text="Timestamp when this record was created.",
                        verbose_name="Date Created",
                    ),
                ),
                (
                    "modified_on",
                    models.DateTimeField(
                        blank=True,
                        editable=False,
                        help_text="Timestamp when this record was last updated.",
                        verbose_name="Date Modified",
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[("NOW", "NOW")],
                        default="NOW",
                        help_text="External taxonomy source for this import.",
                        max_length=16,
                    ),
                ),
                (
                    "started_at",
                    models.DateTimeField(
                        blank=True,
                        editable=False,
                        help_text="Timestamp when the import process started.",
                    ),
                ),
                (
                    "finished_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Timestamp when the import process finished.",
                        null=True,
                    ),
                ),
                (
                    "source_version",
                    models.CharField(
                        blank=True,
                        help_text="Identifier or commit hash describing the imported data.",
                        max_length=255,
                    ),
                ),
                (
                    "counts",
                    models.JSONField(
                        default=dict,
                        help_text="Summary counts for created, updated, deactivated, and related metrics.",
                    ),
                ),
                (
                    "report_json",
                    models.JSONField(
                        default=dict,
                        help_text="Detailed diff or issue information captured during the import.",
                    ),
                ),
                (
                    "ok",
                    models.BooleanField(
                        default=False,
                        help_text="Indicates whether the import completed successfully.",
                    ),
                ),
                ("history_id", models.AutoField(primary_key=True, serialize=False)),
                ("history_date", models.DateTimeField(db_index=True)),
                ("history_change_reason", models.CharField(max_length=100, null=True)),
                (
                    "history_type",
                    models.CharField(
                        choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")],
                        max_length=1,
                    ),
                ),
            ],
            options={
                "verbose_name": "historical Taxonomy Import",
                "verbose_name_plural": "historical Taxonomy Imports",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="TaxonomyImport",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_on",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Timestamp when this record was created.",
                        verbose_name="Date Created",
                    ),
                ),
                (
                    "modified_on",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Timestamp when this record was last updated.",
                        verbose_name="Date Modified",
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[("NOW", "NOW")],
                        default="NOW",
                        help_text="External taxonomy source for this import.",
                        max_length=16,
                    ),
                ),
                (
                    "started_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Timestamp when the import process started.",
                    ),
                ),
                (
                    "finished_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Timestamp when the import process finished.",
                        null=True,
                    ),
                ),
                (
                    "source_version",
                    models.CharField(
                        blank=True,
                        help_text="Identifier or commit hash describing the imported data.",
                        max_length=255,
                    ),
                ),
                (
                    "counts",
                    models.JSONField(
                        default=dict,
                        help_text="Summary counts for created, updated, deactivated, and related metrics.",
                    ),
                ),
                (
                    "report_json",
                    models.JSONField(
                        default=dict,
                        help_text="Detailed diff or issue information captured during the import.",
                    ),
                ),
                (
                    "ok",
                    models.BooleanField(
                        default=False,
                        help_text="Indicates whether the import completed successfully.",
                    ),
                ),
            ],
            options={
                "verbose_name": "Taxonomy Import",
                "verbose_name_plural": "Taxonomy Imports",
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddField(
            model_name="taxonomyimport",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                help_text="User who created this record.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(app_label)s_%(class)s_created",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Created by",
            ),
        ),
        migrations.AddField(
            model_name="taxonomyimport",
            name="modified_by",
            field=models.ForeignKey(
                blank=True,
                help_text="User who most recently updated this record.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(app_label)s_%(class)s_modified",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Modified by",
            ),
        ),
        migrations.AddField(
            model_name="historicaltaxonomyimport",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="User who created this record.",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Created by",
            ),
        ),
        migrations.AddField(
            model_name="historicaltaxonomyimport",
            name="history_user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="historicaltaxonomyimport",
            name="modified_by",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="User who most recently updated this record.",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Modified by",
            ),
        ),
    ]
