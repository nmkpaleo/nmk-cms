# Generated by Django 4.1.13 on 2024-06-12 09:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0004_accession_comment_accession_type_status_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='accession',
            name='comment',
            field=models.TextField(null=True),
        ),
    ]
