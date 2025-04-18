# Generated by Django 4.2.18 on 2025-01-28 14:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0021_alter_media_license_alter_media_media_location'),
    ]

    operations = [
        migrations.AlterField(
            model_name='media',
            name='license',
            field=models.CharField(choices=[('CC0', 'Public Domain (CC0)'), ('CC_BY', 'Creative Commons - Attribution (CC BY)'), ('CC_BY_SA', 'Creative Commons - Attribution-ShareAlike (CC BY-SA)'), ('CC_BY_NC', 'Creative Commons - Attribution-NonCommercial (CC BY-NC)'), ('CC_BY_ND', 'Creative Commons - Attribution-NoDerivatives (CC BY-ND)'), ('CC_BY_NC_SA', 'Creative Commons - Attribution-NonCommercial-ShareAlike (CC BY-NC-SA)'), ('CC_BY_NC_ND', 'Creative Commons - Attribution-NonCommercial-NoDerivatives (CC BY-NC-ND)'), ('GFDL', 'GNU Free Documentation License (GFDL)'), ('OGL', 'Open Government License (OGL)'), ('RF', 'Royalty-Free (RF)'), ('RM', 'Rights-Managed (RM)'), ('EDITORIAL', 'Editorial Use Only'), ('CUSTOM_ATTRIBUTION', 'Attribution (Custom License)'), ('SHAREWARE', 'Shareware/Donationware'), ('EULA', 'End-User License Agreement (EULA)')], default='CC0', help_text='License information for the media file', max_length=30),
        ),
    ]
