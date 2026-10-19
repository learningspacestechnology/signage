"""Create the "Exempt from inactivity removal" group, empty.

Accounts with no sign-in for ACCOUNT_INACTIVITY_DAYS are deactivated and later
deleted (screens.account_inactivity). Some accounts are meant to sit unused —
the emergency password account kept for when Microsoft sign-in breaks, service
accounts — and an admin exempts those by adding them to this group.

It starts empty on purpose: nothing here can tell which accounts those are.

The permission row is created here rather than left to Django, because
``create_permissions`` runs on ``post_migrate`` — after every migration in the
run, too late for this one. Its name must match ``AccountLifecycle.Meta``
exactly: ``create_permissions`` skips a (content type, codename) pair that
already exists, so a mismatch here would never be corrected.
"""

from django.db import migrations

GROUP_NAME = "Exempt from inactivity removal"
CODENAME = "exempt_from_inactivity_removal"
PERMISSION_NAME = "Exempt from removal after inactivity"


def forwards(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")

    content_type, _ = ContentType.objects.get_or_create(
        app_label="screens", model="accountlifecycle")
    permission, _ = Permission.objects.get_or_create(
        content_type=content_type, codename=CODENAME,
        defaults={"name": PERMISSION_NAME})
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    group.permissions.add(permission)


class Migration(migrations.Migration):

    dependencies = [
        ("screens", "0039_accountlifecycle"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        # Not reversed: an admin may have added members by then, and deleting
        # the group would silently un-exempt them.
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
