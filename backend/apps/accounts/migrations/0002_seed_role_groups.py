from django.db import migrations


ROLE_NAMES = (
    "Admin",
    "Manager",
    "Cashier",
    "Inventory/Store Staff",
)


def seed_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    database = schema_editor.connection.alias
    for name in ROLE_NAMES:
        Group.objects.using(database).get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(seed_roles, migrations.RunPython.noop),
    ]
