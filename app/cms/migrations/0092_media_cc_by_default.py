from django.db import migrations, models


def migrate_nmk_media_to_cc_by(apps, schema_editor):
    Media = apps.get_model("cms", "Media")
    Media.objects.filter(license__in=["CC0", "CC_BY"]).update(license="CC_BY_NC")


class Migration(migrations.Migration):
    dependencies = [("cms", "0091_openai_billing")]

    operations = [
        migrations.RunPython(migrate_nmk_media_to_cc_by, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="media",
            name="license",
            field=models.CharField(
                max_length=30,
                choices=[
                    ("CC0", "Public Domain (CC0)"),
                    ("CC_BY", "Creative Commons - Attribution (CC BY)"),
                    ("CC_BY_SA", "Creative Commons - Attribution-ShareAlike (CC BY-SA)"),
                    ("CC_BY_NC", "Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)"),
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
                default="CC_BY_NC",
                help_text="License information for the media file",
            ),
        ),
    ]
