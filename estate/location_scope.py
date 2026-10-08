"""Scoping querysets to the locations a request's user may see.

See `estate.models.access` for the model. The rules:

- Superusers and holders of ``estate.access_all_locations`` see everything.
- Everyone else sees the union of what their location groups grant, and
  **nothing** if they are in no group. There is deliberately no fail-open
  branch: unlike `screens.team_scope.scope_to_active_team`, which treats a
  request the team middleware never touched as "all teams", this depends only
  on ``request.user``, so it behaves the same on every path.
- A room grant reveals its building and campus; a building or campus grant
  reveals everything beneath it.
- A screen in a building but no room needs that building granted outright,
  by a building or campus grant. A room grant in the building is not enough.

Every filter here goes through a ``pk__in`` subquery rather than a join. A join
across the three grant tables would repeat rows once per matching grant, and a
join from Campus or Building down to rooms would be reused by any ``Count``
annotated afterwards, silently changing what it counts.
"""

from django.core.exceptions import FieldDoesNotExist
from django.db.models import Q

from .models import Building, Campus, LocationGroup, LocationGroupMembership, Room

ACCESS_ALL_PERM = 'estate.access_all_locations'

#: The auth Group migration 0005 creates. Informational: nothing keys on the
#: name, and an admin may rename it.
ALL_LOCATIONS_GROUP_NAME = 'All locations'


class _AllLocationsSentinel:
    def __repr__(self):
        return 'ALL_LOCATIONS'


#: Returned by `visible_room_ids` for a user who is not location-restricted.
#: Compare with ``is``.
ALL_LOCATIONS = _AllLocationsSentinel()


def sees_all_locations(request):
    """Whether the request's user is exempt from location scoping.

    ``has_perm`` already answers True for an active superuser and False for an
    anonymous or inactive user. Cached on the request, since one page asks
    many times.
    """
    cached = getattr(request, '_sees_all_locations', None)
    if cached is None:
        cached = request.user.has_perm(ACCESS_ALL_PERM)
        request._sees_all_locations = cached
    return cached


def rooms_granted_by(groups):
    """Every room the given location groups cover, as a lazy Room queryset.

    ``groups`` is anything usable with ``__in`` against LocationGroup pks — a
    queryset, a ``values()`` subquery or a list.

    Three separate subqueries OR'd together, one per kind of grant, so a room
    granted twice over (directly and through its building) still appears once.
    """
    through = LocationGroup
    by_room = (through.rooms.through.objects
               .filter(locationgroup__in=groups).values('room'))
    by_building = (through.buildings.through.objects
                   .filter(locationgroup__in=groups).values('building'))
    by_campus = (through.campuses.through.objects
                 .filter(locationgroup__in=groups).values('campus'))
    return Room.objects.filter(
        Q(pk__in=by_room)
        | Q(building__in=by_building)
        | Q(building__in=Building.objects.filter(campus__in=by_campus).values('pk'))
    )


def buildings_wholly_granted_by(groups):
    """Every building a building or campus grant covers, as a lazy queryset.

    Narrower than the buildings a user can *see*: a room grant reveals its
    building, but covers only that room in it, so it does not reach a screen
    placed in the building with no room.
    """
    through = LocationGroup
    by_building = (through.buildings.through.objects
                   .filter(locationgroup__in=groups).values('building'))
    by_campus = (through.campuses.through.objects
                 .filter(locationgroup__in=groups).values('campus'))
    return Building.objects.filter(Q(pk__in=by_building) | Q(campus__in=by_campus))


def _user_groups(request):
    return LocationGroupMembership.objects.filter(
        user_id=request.user.pk).values('group')


def visible_room_ids(request):
    """`ALL_LOCATIONS`, or a lazy subquery of the room pks the user may see.

    Kept as a subquery rather than evaluated: a campus grant can cover
    thousands of rooms, more than SQLite accepts as query parameters.
    """
    if sees_all_locations(request):
        return ALL_LOCATIONS
    return rooms_granted_by(_user_groups(request)).order_by().values('pk')


def wholly_visible_building_ids(request):
    """`ALL_LOCATIONS`, or a lazy subquery of the buildings granted outright."""
    if sees_all_locations(request):
        return ALL_LOCATIONS
    return (buildings_wholly_granted_by(_user_groups(request))
            .order_by().values('pk'))


def has_any_location(request):
    """Whether the user can see at least one room."""
    ids = visible_room_ids(request)
    return ids is ALL_LOCATIONS or Room.objects.filter(pk__in=ids).exists()


def scope_to_locations(qs, request):
    """Filter a Room, Building, Campus or room-bearing queryset to the user's places.

    A model qualifies as room-bearing through a ForeignKey named ``room`` to
    `estate.Room` — `screens.Screen` today. A row with a room is scoped by the
    room alone. One with no room is visible to a restricted user only if the
    model also has a ``building`` ForeignKey to `estate.Building` and that
    building is granted outright, by a building or campus grant; with neither,
    no grant can cover it. Anything else raises rather than passing through
    unfiltered.
    """
    ids = visible_room_ids(request)
    if ids is ALL_LOCATIONS:
        return qs
    model = qs.model
    if model is Room:
        return qs.filter(pk__in=ids)
    if model is Building:
        return qs.filter(pk__in=Room.objects.filter(pk__in=ids).values('building'))
    if model is Campus:
        return qs.filter(
            pk__in=Room.objects.filter(pk__in=ids).values('building__campus'))
    if _fk_to(model, 'room', Room):
        if not _fk_to(model, 'building', Building):
            return qs.filter(room__in=ids)
        # room__isnull on the second branch, rather than trusting `building` to
        # match the room: a row with a room answers to its room, the field
        # nothing can let drift.
        return qs.filter(
            Q(room__in=ids)
            | Q(room__isnull=True,
                building__in=wholly_visible_building_ids(request)))
    raise TypeError(f"Don't know how to location-scope {model.__name__}")


def _fk_to(model, name, target):
    try:
        field = model._meta.get_field(name)
    except FieldDoesNotExist:
        return False
    return field.many_to_one and field.related_model is target


def scope_screens(qs, request):
    """Screens the request may see: its active team's, within its locations."""
    from screens.team_scope import scope_to_active_team

    return scope_to_locations(scope_to_active_team(qs, request), request)
