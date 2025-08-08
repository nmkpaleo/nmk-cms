from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0041_alter_media_format_helptext'),
    ]

    operations = [
        migrations.AddField(
            model_name='accessionrow',
            name='status',
            field=models.CharField(
                blank=True,
                null=True,
                max_length=10,
                choices=[('present', 'Present'), ('missing', 'Missing'), ('unknown', 'Unknown')],
                help_text='Inventory status of the specimen',
            ),
        ),
    ]
