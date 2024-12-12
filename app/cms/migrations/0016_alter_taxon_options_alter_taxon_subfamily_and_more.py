# Generated by Django 4.2.16 on 2024-11-23 13:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0015_taxon_taxon_name_alter_taxon_infraspecific_epithet_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='taxon',
            options={'ordering': ['class_name', 'order', 'family', 'genus', 'species'], 'verbose_name': 'Taxon', 'verbose_name_plural': 'Taxa'},
        ),
        migrations.AlterField(
            model_name='taxon',
            name='subfamily',
            field=models.CharField(blank=True, default='', max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='taxon',
            name='superfamily',
            field=models.CharField(blank=True, default='', max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='taxon',
            name='taxon_rank',
            field=models.CharField(choices=[('kingdom', 'Kingdom'), ('phylum', 'Phylum'), ('class', 'Class'), ('order', 'Order'), ('family', 'Family'), ('genus', 'Genus'), ('species', 'Species'), ('subspecies', 'Subspecies')], max_length=50),
        ),
        migrations.AlterField(
            model_name='taxon',
            name='tribe',
            field=models.CharField(blank=True, default='', max_length=255, null=True),
        ),
        migrations.AddConstraint(
            model_name='taxon',
            constraint=models.UniqueConstraint(fields=('taxon_rank', 'taxon_name', 'scientific_name_authorship'), name='unique_taxon_rank_name_authorship'),
        ),
    ]