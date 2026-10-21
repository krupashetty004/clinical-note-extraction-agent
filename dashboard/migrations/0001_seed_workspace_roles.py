from django.db import migrations


ROLE_NAMES = ("Doctor", "Administrator")


def create_workspace_roles(apps, schema_editor):
    """Create the initial workspace role groups."""

    Group = apps.get_model("auth", "Group")
    database_alias = schema_editor.connection.alias

    for role_name in ROLE_NAMES:
        Group.objects.using(database_alias).get_or_create(
            name=role_name,
        )


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(
            create_workspace_roles,
            reverse_code=migrations.RunPython.noop,
        ),
    ]