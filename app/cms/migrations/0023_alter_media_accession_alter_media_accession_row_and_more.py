# Generated by Django 4.2.18 on 2025-01-28 15:01

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0022_alter_media_license'),
    ]

    operations = [
        migrations.AlterField(
            model_name='media',
            name='accession',
            field=models.ForeignKey(blank=True, help_text='Accession this media belongs to', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='media', to='cms.accession'),
        ),
        migrations.AlterField(
            model_name='media',
            name='accession_row',
            field=models.ForeignKey(blank=True, help_text='Accession row this media belongs to', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='media', to='cms.accessionrow'),
        ),
        migrations.AlterField(
            model_name='media',
            name='file_name',
            field=models.CharField(blank=True, help_text='The name of the media file', max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='media',
            name='format',
            field=models.CharField(blank=True, choices=[('jpg', 'JPG'), ('png', 'PNG'), ('mp4', 'MP4'), ('mp3', 'MP3'), ('pdf', 'PDF'), ('txt', 'TXT'), ('docx', 'DOCX'), ('other', 'Other')], help_text='File format of the media (e.g., jpg, png, mp4, etc.)', max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name='media',
            name='rights_holder',
            field=models.CharField(blank=True, help_text='The individual or organization holding rights to the media', max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='media',
            name='type',
            field=models.CharField(blank=True, choices=[('photo', 'Photo'), ('video', 'Video'), ('audio', 'Audio'), ('document', 'Document'), ('text', 'Text'), ('other', 'Other')], help_text='Type of the media (e.g., photo, video, etc.)', max_length=50, null=True),
        ),
    ]
