"""Keep every existing staff user seeing every location.

Location access fails closed: a staff user in no location group sees no
screens. Without this migration the deploy that introduces location groups
would blank the screen list for everyone but superusers. Instead every staff
user who already exists joins an "All locations" auth Group carrying
``estate.access_all_locations``, and an admin narrows people down from there.

Inactive staff are included so that reactivating someone restores what they
had. Non-staff are not: they have no admin access today, so they lose nothing.

The permission row is created here rather than left to Django, because
``create_permissions`` runs on ``post_migrate`` — after every migration in the
run, too late for this one. Its name must match ``LocationGroup.Meta``
exactly: ``create_permissions`` skips a (content type, codename) pair that
already exists, so a mismatch here would never be corrected.
"""

from django.db import migrations

GROUP_NAME = "All locations"
CODENAME = "access_all_locations"
PERMISSION_NAME = "Can see all locations"


def forwards(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("auth", "User")

    content_type, _ = ContentType.objects.get_or_create(
        app_label="estate", model="locationgroup")
    permission, _ = Permission.objects.get_or_create(
        content_type=content_type, codename=CODENAME,
        defaults={"name": PERMISSION_NAME})
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    group.permissions.add(permission)
    group.user_set.add(*User.objects.filter(is_staff=True))


class Migration(migrations.Migration):

    dependencies = [
        ("estate", "0004_location_groups"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        # Not reversible in any useful sense: by the time anyone rolls back,
        # an admin may have edited the group, and deleting it would take their
        # changes with it.
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
