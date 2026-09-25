from django.db import migrations


def create_researchers_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Researchers")


def remove_researchers_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Researchers").delete()


class Migration(migrations.Migration):
    dependencies = [("cms", "0093_alter_historicalmedia_license")]
    operations = [migrations.RunPython(create_researchers_group, remove_researchers_group)]