from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0040_accessionnumberseries_created_by_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='media',
            name='format',
            field=models.CharField(
                max_length=50,
                null=True,
                blank=True,
                choices=[('jpg', 'JPG'), ('jpeg', 'JPEG'), ('png', 'PNG'), ('gif', 'GIF'), ('bmp', 'BMP')],
                help_text="File format of the media (supported formats: 'jpg', 'jpeg', 'png', 'gif', 'bmp')",
            ),
        ),
    ]

