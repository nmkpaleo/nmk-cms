# Generated manually for merge permissions
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0061_llmusagerecord_processing_seconds_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="fieldslip",
            options={
                "ordering": ["field_number"],
                "verbose_name": "Field Slip",
                "verbose_name_plural": "Field Slips",
                "permissions": [("can_merge", "Can merge field slip records")],
            },
        ),
        migrations.AlterModelOptions(
            name="storage",
            options={
                "verbose_name": "Storage",
                "verbose_name_plural": "Storages",
                "permissions": [("can_merge", "Can merge storage records")],
            },
        ),
        migrations.AlterModelOptions(
            name="reference",
            options={
                "verbose_name": "Reference",
                "verbose_name_plural": "References",
                "permissions": [("can_merge", "Can merge reference records")],
            },
        ),
    ]
