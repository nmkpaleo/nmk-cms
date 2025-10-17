from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0064_mergelog_relation_actions"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="taxon",
            options={
                "ordering": ["class_name", "order", "family", "genus", "species"],
                "permissions": [("can_sync", "Can sync external taxonomy data")],
                "verbose_name": "Taxon",
                "verbose_name_plural": "Taxa",
            },
        ),
        migrations.AddField(
            model_name="historicalidentification",
            name="taxon_record",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="Linked taxon from the controlled taxonomy.",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="cms.taxon",
            ),
        ),
        migrations.AddField(
            model_name="historicaltaxon",
            name="accepted_taxon",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="Accepted taxon referenced when this record is a synonym.",
                limit_choices_to={"status": "accepted"},
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="cms.taxon",
            ),
        ),
        migrations.AddField(
            model_name="historicaltaxon",
            name="author_year",
            field=models.CharField(
                blank=True,
                help_text="Authorship information associated with the name.",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="historicaltaxon",
            name="external_id",
            field=models.CharField(
                blank=True,
                help_text="Stable identifier supplied by the external source.",
                max_length=191,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="historicaltaxon",
            name="external_source",
            field=models.CharField(
                choices=[("NOW", "NOW"), ("PBDB", "PBDB"), ("LEGACY", "Legacy")],
                default="LEGACY",
                help_text="External source that provided this taxon.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="historicaltaxon",
            name="is_active",
            field=models.BooleanField(
                default=True,
                help_text="Indicates whether the taxon should be treated as active.",
            ),
        ),
        migrations.AddField(
            model_name="historicaltaxon",
            name="name",
            field=models.CharField(
                blank=True,
                help_text="Full scientific name for the taxon.",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="historicaltaxon",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="Immediate parent in the taxonomic hierarchy, when available.",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="cms.taxon",
            ),
        ),
        migrations.AddField(
            model_name="historicaltaxon",
            name="rank",
            field=models.CharField(
                blank=True,
                choices=[
                    ("kingdom", "Kingdom"),
                    ("phylum", "Phylum"),
                    ("class", "Class"),
                    ("order", "Order"),
                    ("superfamily", "Superfamily"),
                    ("family", "Family"),
                    ("subfamily", "Subfamily"),
                    ("tribe", "Tribe"),
                    ("genus", "Genus"),
                    ("species", "Species"),
                    ("subspecies", "Subspecies"),
                ],
                help_text="Taxonomic rank represented by this record.",
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="historicaltaxon",
            name="source_version",
            field=models.CharField(
                blank=True,
                help_text="Version or commit identifier for the external source.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="historicaltaxon",
            name="status",
            field=models.CharField(
                choices=[("accepted", "Accepted"), ("synonym", "Synonym"), ("invalid", "Invalid")],
                default="accepted",
                help_text="Curation status for the taxon record.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="identification",
            name="taxon_record",
            field=models.ForeignKey(
                blank=True,
                help_text="Linked taxon from the controlled taxonomy.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="identifications",
                to="cms.taxon",
            ),
        ),
        migrations.AddField(
            model_name="taxon",
            name="accepted_taxon",
            field=models.ForeignKey(
                blank=True,
                help_text="Accepted taxon referenced when this record is a synonym.",
                limit_choices_to={"status": "accepted"},
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="synonyms",
                to="cms.taxon",
            ),
        ),
        migrations.AddField(
            model_name="taxon",
            name="author_year",
            field=models.CharField(
                blank=True,
                help_text="Authorship information associated with the name.",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="taxon",
            name="external_id",
            field=models.CharField(
                blank=True,
                help_text="Stable identifier supplied by the external source.",
                max_length=191,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="taxon",
            name="external_source",
            field=models.CharField(
                choices=[("NOW", "NOW"), ("PBDB", "PBDB"), ("LEGACY", "Legacy")],
                default="LEGACY",
                help_text="External source that provided this taxon.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="taxon",
            name="is_active",
            field=models.BooleanField(
                default=True,
                help_text="Indicates whether the taxon should be treated as active.",
            ),
        ),
        migrations.AddField(
            model_name="taxon",
            name="name",
            field=models.CharField(
                blank=True,
                help_text="Full scientific name for the taxon.",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="taxon",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                help_text="Immediate parent in the taxonomic hierarchy, when available.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="children",
                to="cms.taxon",
            ),
        ),
        migrations.AddField(
            model_name="taxon",
            name="rank",
            field=models.CharField(
                blank=True,
                choices=[
                    ("kingdom", "Kingdom"),
                    ("phylum", "Phylum"),
                    ("class", "Class"),
                    ("order", "Order"),
                    ("superfamily", "Superfamily"),
                    ("family", "Family"),
                    ("subfamily", "Subfamily"),
                    ("tribe", "Tribe"),
                    ("genus", "Genus"),
                    ("species", "Species"),
                    ("subspecies", "Subspecies"),
                ],
                help_text="Taxonomic rank represented by this record.",
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="taxon",
            name="source_version",
            field=models.CharField(
                blank=True,
                help_text="Version or commit identifier for the external source.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="taxon",
            name="status",
            field=models.CharField(
                choices=[("accepted", "Accepted"), ("synonym", "Synonym"), ("invalid", "Invalid")],
                default="accepted",
                help_text="Curation status for the taxon record.",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="historicaltaxon",
            name="taxon_rank",
            field=models.CharField(
                choices=[
                    ("kingdom", "Kingdom"),
                    ("phylum", "Phylum"),
                    ("class", "Class"),
                    ("order", "Order"),
                    ("superfamily", "Superfamily"),
                    ("family", "Family"),
                    ("subfamily", "Subfamily"),
                    ("tribe", "Tribe"),
                    ("genus", "Genus"),
                    ("species", "Species"),
                    ("subspecies", "Subspecies"),
                ],
                help_text="Taxonomic rank represented by this record.",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="taxon",
            name="taxon_rank",
            field=models.CharField(
                choices=[
                    ("kingdom", "Kingdom"),
                    ("phylum", "Phylum"),
                    ("class", "Class"),
                    ("order", "Order"),
                    ("superfamily", "Superfamily"),
                    ("family", "Family"),
                    ("subfamily", "Subfamily"),
                    ("tribe", "Tribe"),
                    ("genus", "Genus"),
                    ("species", "Species"),
                    ("subspecies", "Subspecies"),
                ],
                help_text="Taxonomic rank represented by this record.",
                max_length=50,
            ),
        ),
        migrations.AddIndex(
            model_name="taxon",
            index=models.Index(fields=["external_source", "external_id"], name="taxon_external_idx"),
        ),
        migrations.AddIndex(
            model_name="taxon",
            index=models.Index(fields=["status"], name="taxon_status_idx"),
        ),
        migrations.AddIndex(
            model_name="taxon",
            index=models.Index(fields=["rank"], name="taxon_rank_idx"),
        ),
        migrations.AddIndex(
            model_name="taxon",
            index=models.Index(fields=["is_active"], name="taxon_active_idx"),
        ),
        migrations.AddConstraint(
            model_name="taxon",
            constraint=models.UniqueConstraint(
                condition=(
                    models.Q(external_id__isnull=False, external_source__isnull=False)
                    & ~models.Q(external_id="")
                ),
                fields=("external_source", "external_id"),
                name="unique_taxon_external_source_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="taxon",
            constraint=models.CheckConstraint(
                check=
                (
                    models.Q(status="accepted", accepted_taxon__isnull=True)
                    | models.Q(status="synonym", accepted_taxon__isnull=False)
                    | models.Q(status="invalid")
                ),
                name="taxon_status_consistency",
            ),
        ),
    ]
