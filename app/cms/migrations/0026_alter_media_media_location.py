# Generated by Django 4.2.18 on 2025-01-28 15:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0025_alter_media_format'),
    ]

    operations = [
        migrations.AlterField(
            model_name='media',
            name='media_location',
            field=models.ImageField(upload_to='media/'),
        ),
    ]
