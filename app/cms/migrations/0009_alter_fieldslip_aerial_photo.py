# Generated by Django 4.1.13 on 2024-09-23 15:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0008_remove_fieldslip_accession'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fieldslip',
            name='aerial_photo',
            field=models.ImageField(blank=True, null=True, upload_to='aerial_photos/'),
        ),
    ]
