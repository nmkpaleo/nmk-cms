from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cms", "0092_media_cc_by_default")]

    operations = [
        migrations.AlterField(
            model_name="historicalmedia",
            name="license",
            field=models.CharField(
                max_length=30,
                choices=[
                    ("CC0", "Public Domain (CC0)"),
                    ("CC_BY", "Creative Commons Attribution 4.0 International (CC BY 4.0)"),
                    ("CC_BY_SA", "Creative Commons - Attribution-ShareAlike (CC BY-SA)"),
                    ("CC_BY_NC", "Creative Commons - Attribution-NonCommercial (CC BY-NC)"),
                    ("CC_BY_ND", "Creative Commons - Attribution-NoDerivatives (CC BY-ND)"),
                    ("CC_BY_NC_SA", "Creative Commons - Attribution-NonCommercial-ShareAlike (CC BY-NC-SA)"),
                    ("CC_BY_NC_ND", "Creative Commons - Attribution-NonCommercial-NoDerivatives (CC BY-NC-ND)"),
                    ("GFDL", "GNU Free Documentation License (GFDL)"),
                    ("OGL", "Open Government License (OGL)"),
                    ("RF", "Royalty-Free (RF)"),
                    ("RM", "Rights-Managed (RM)"),
                    ("EDITORIAL", "Editorial Use Only"),
                    ("CUSTOM_ATTRIBUTION", "Attribution (Custom License)"),
                    ("SHAREWARE", "Shareware/Donationware"),
                    ("EULA", "End-User License Agreement (EULA)"),
                ],
                default="CC_BY",
                help_text="License information for the media file",
            ),
        ),
    ]
