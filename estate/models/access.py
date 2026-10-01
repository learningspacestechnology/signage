"""Location groups: which parts of the estate a user may see.

The third of three independent access axes. A Team decides *whose* content you
see, an auth Group decides *what* you can do, and a location group decides
*where* — which campuses, buildings and rooms, and so which screens.

Fail closed: a staff user in no location group sees no screens and no estate
rows. Superusers and holders of ``estate.access_all_locations`` see everything;
migration 0005 grants that, through an "All locations" auth Group, to every
staff user who existed before this model did. The scoping itself lives in
`estate.location_scope`.
"""

from django.conf import settings
from django.db import models
from django.db.models import Exists, OuterRef, Q

from .building import Building
from .campus import Campus
from .room import Room


class LocationGroup(models.Model):
    """A named set of places, granted to its members.

    A user's places are the union over every group they are in. Each grant
    covers everything beneath it: a campus grant covers all its buildings and
    rooms, a building grant all its rooms — including rooms the nightly sync
    adds later. A room grant covers just that room, and so reveals its building
    and campus without the rest of them.
    """

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True, default='')

    campuses = models.ManyToManyField(
        Campus, blank=True, related_name='location_groups',
        help_text="Every building and room on these campuses.")
    buildings = models.ManyToManyField(
        Building, blank=True, related_name='location_groups',
        help_text="Every room in these buildings, including rooms added later.")
    rooms = models.ManyToManyField(
        Room, blank=True, related_name='location_groups',
        help_text="Just these rooms.")

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through='LocationGroupMembership',
        blank=True, related_name='location_groups')

    class Meta:
        ordering = ['name']
        permissions = [('access_all_locations', 'Can see all locations')]

    def __str__(self):
        return self.name


class LocationGroupMembership(models.Model):
    """A user's membership of a location group.

    An explicit through model, like `screens.TeamMembership`, so membership can
    be edited inline from both the group and the user.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='location_group_memberships')
    group = models.ForeignKey(
        LocationGroup, on_delete=models.CASCADE, related_name='memberships')

    class Meta:
        unique_together = ('user', 'group')
        verbose_name = 'location group membership'

    def __str__(self):
        return f"{self.user} ∈ {self.group}"


def stale_grants_q():
    """Location groups granting a campus, building or room the datastore dropped.

    Such a grant is kept, flagged, rather than silently removed: the sync never
    deletes a row something points at. It still needs a person, though. The
    usual cause is an upstream building rename, which the sync sees as a new
    building — so a grant on the old one now covers no rooms at all, and the
    group's members quietly lose sight of that building's screens.
    """
    def stale(field, related):
        through = getattr(LocationGroup, field).through
        return Exists(through.objects.filter(
            locationgroup=OuterRef('pk'),
            **{f'{related}__missing_from_source': True}))

    return (Q(stale('campuses', 'campus'))
            | Q(stale('buildings', 'building'))
            | Q(stale('rooms', 'room')))
