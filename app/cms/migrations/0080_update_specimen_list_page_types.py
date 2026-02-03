from django.db import migrations


def migrate_page_types(apps, schema_editor):
    SpecimenListPage = apps.get_model("cms", "SpecimenListPage")
    SpecimenListPage.objects.filter(page_type="specimen_list").update(
        page_type="specimen_list_details"
    )

    HistoricalSpecimenListPage = apps.get_model("cms", "HistoricalSpecimenListPage")
    HistoricalSpecimenListPage.objects.filter(page_type="specimen_list").update(
        page_type="specimen_list_details"
    )


def reverse_page_types(apps, schema_editor):
    SpecimenListPage = apps.get_model("cms", "SpecimenListPage")
    SpecimenListPage.objects.filter(page_type="specimen_list_details").update(
        page_type="specimen_list"
    )

    HistoricalSpecimenListPage = apps.get_model("cms", "HistoricalSpecimenListPage")
    HistoricalSpecimenListPage.objects.filter(page_type="specimen_list_details").update(
        page_type="specimen_list"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0079_specimenlistpage_classification"),
    ]

    operations = [
        migrations.RunPython(migrate_page_types, reverse_page_types),
    ]
