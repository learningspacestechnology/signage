"""Shared test helpers for location access."""

from django.contrib.auth.models import Group, Permission, User

from estate.location_scope import ALL_LOCATIONS_GROUP_NAME


def grant_all_locations(user):
    """Exempt ``user`` from location scoping, as migration 0005 does for staff.

    Location access fails closed, so any test that logs in a non-superuser to
    look at screens or the estate needs this — or a location group — or it
    sees nothing. ``get_or_create`` rather than relying on the migration's
    group, which a TransactionTestCase flush would have removed.

    Returns a fresh copy of the user, since ``has_perm`` caches on the object.
    """
    group, _ = Group.objects.get_or_create(name=ALL_LOCATIONS_GROUP_NAME)
    group.permissions.add(Permission.objects.get(
        content_type__app_label='estate', codename='access_all_locations'))
    user.groups.add(group)
    return User.objects.get(pk=user.pk)
