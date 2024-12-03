# Generated by Django 4.2.16 on 2024-11-20 03:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0013_accessionrow_element_taxon_person_natureofspecimen_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reference',
            name='issue',
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.AlterField(
            model_name='reference',
            name='volume',
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.AlterField(
            model_name='reference',
            name='year',
            field=models.CharField(max_length=4),
        ),
    ]
