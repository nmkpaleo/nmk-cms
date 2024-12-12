# Generated by Django 4.2.16 on 2024-11-23 19:00

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0016_alter_taxon_options_alter_taxon_subfamily_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='element',
            options={'ordering': ['parent_element__name', 'name']},
        ),
        migrations.AlterField(
            model_name='element',
            name='parent_element',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='cms.element'),
        ),
    ]