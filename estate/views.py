"""Custom admin pages for the estate directory.

Plain function views returning a TemplateResponse built on
``admin.site.each_context`` — the project's established shape for an admin page
that is not a ModelAdmin, matching `playlist_tree_view` in screens/admin.py and
the O365 views in room_schedules/admin.py.
"""

from collections import defaultdict
from itertools import groupby

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.http import require_POST

from estate.admin import dispatch_sync
from estate.location_scope import (scope_screens, scope_to_locations,
                                   sees_all_locations)
from estate.matching import suggest_buildings, suggest_rooms
from estate.models import Building, BuildingLink, Room, RoomLink
from screens.models import Screen
from screens.models.screen import ScreenStatus


@require_POST
def estate_sync_now_view(request):
    # The sync refreshes the whole estate, so it belongs to those who can see
    # the whole estate.
    if not sees_all_locations(request):
        raise PermissionDenied
    referer = request.META.get('HTTP_REFERER') or reverse(
        'admin:estate_room_changelist')
    return dispatch_sync(request, referer)


def building_screens_view(request, building_id):
    """Every screen in one building, and every room in it with no screen.

    A page rather than a filtered changelist link, because the operational
    question at building level is the *left join* — which rooms are dark. A
    changelist can only enumerate screens. The filtered changelist is still
    linked from here as the "see these in the full list" route.
    """
    # admin.site.admin_view only enforces staff + active, so gate the content
    # explicitly rather than leaning on the sidebar's permission lambda.
    if not request.user.has_perm('screens.view_screen'):
        raise PermissionDenied

    # A building outside the requester's location groups is a 404, as it is
    # in the building changelist, rather than a page listing its dark rooms.
    building = get_object_or_404(
        scope_to_locations(Building.objects.select_related('campus'), request),
        pk=building_id)

    # Scoped first, then annotated — the same layering as
    # ScreenAdmin.get_queryset, so this page's badge and the changelist's can
    # never disagree about a screen's status.
    screens = (
        scope_screens(Screen.objects.all(), request)
        .filter(room__building=building)
        .with_status()
        .select_related('room')
        .order_by('room__name', 'name')
    )
    screens = list(screens)

    counts = {status: 0 for status in (
        ScreenStatus.ONLINE, ScreenStatus.ATTENTION, ScreenStatus.OFFLINE)}
    for screen in screens:
        counts[screen.derived_status] = counts.get(screen.derived_status, 0) + 1

    occupied = {screen.room_id for screen in screens}
    # Scoped too: a user granted one room in the building sees that room, not
    # the rest of the building's.
    dark_rooms = (scope_to_locations(building.rooms.all(), request)
                  .exclude(pk__in=occupied).order_by('name'))

    changelist = (
        f"{reverse('admin:screens_screen_changelist')}"
        f"?room__building__id__exact={building.pk}"
    )

    context = {
        **admin.site.each_context(request),
        'title': f"Screens in {building.name}",
        'opts': Screen._meta,
        'building': building,
        'screens': screens,
        'online_count': counts[ScreenStatus.ONLINE],
        'attention_count': counts[ScreenStatus.ATTENTION],
        'offline_count': counts[ScreenStatus.OFFLINE],
        'dark_rooms': dark_rooms,
        'changelist_url': changelist,
        'building_url': reverse('admin:estate_building_change', args=[building.pk]),
    }
    return TemplateResponse(request, 'admin/estate/building_screens.html', context)


# ---------------------------------------------------------------------------
# Linking the room_schedules display records to the estate directory.
#
# Buildings first, rooms second. Once a display building is linked, the room
# candidates collapse from the whole estate to the few dozen in that building —
# and labels like "2.14" only become unambiguous inside a building, so matching
# rooms globally would produce confident nonsense.
# ---------------------------------------------------------------------------

LINK_PERMISSION = 'room_schedules.change_room'


def _tab_context():
    return {
        'assigned_url': reverse('admin:room_schedules_o365_assigned'),
        'unassigned_url': reverse('admin:room_schedules_o365_unassigned'),
        'sync_now_url': reverse('admin:room_schedules_o365_sync_now'),
        'estate_links_url': reverse('admin:estate_room_links'),
    }


def _chosen(request, field):
    """The first non-empty value for `field`.

    The form offers the same field name twice — as suggestion radios and as a
    full-list select — so the operator can use either. QueryDict.get returns
    the *last* value, which would be the select's empty option whenever a radio
    was used, so take the first thing actually chosen instead.
    """
    for value in request.POST.getlist(field):
        if value:
            return value
    return None


def _link_building(request):
    from room_schedules.models import Building as DisplayBuilding

    display = get_object_or_404(
        DisplayBuilding, pk=request.POST.get('display_building_id'))
    estate_id = _chosen(request, 'estate_building_id')
    if not estate_id:
        messages.error(request, f"Choose a building to link {display.name} to.")
        return

    estate = get_object_or_404(Building, pk=estate_id)
    BuildingLink.objects.update_or_create(
        display_building=display,
        defaults={'estate_building': estate, 'linked_by': request.user},
    )
    messages.success(request, f"Linked {display.name} to {estate.name}.")


def _link_room(request):
    from room_schedules.models import Room as DisplayRoom

    display = get_object_or_404(DisplayRoom, pk=request.POST.get('display_room_id'))
    estate_id = _chosen(request, 'estate_room_id')
    if not estate_id:
        messages.error(request, f"Choose a room to link {display.label} to.")
        return

    estate = get_object_or_404(Room, pk=estate_id)
    # estate_room is unique, so two display rooms pointing at one estate room
    # is a data-entry mistake. Checked here rather than caught as an
    # IntegrityError, which would poison the surrounding transaction.
    taken = RoomLink.objects.filter(estate_room=estate).exclude(
        display_room=display).first()
    if taken is not None:
        messages.error(
            request,
            f"{estate} is already linked to {taken.display_room.label}. Unlink "
            f"that first if {display.label} is the correct one.")
        return

    RoomLink.objects.update_or_create(
        display_room=display,
        defaults={'estate_room': estate, 'linked_by': request.user},
    )
    messages.success(request, f"Linked {display.label} to {estate}.")


def _unlink(request):
    model = {'building': BuildingLink, 'room': RoomLink}.get(
        request.POST.get('link_kind'))
    if model is None:
        return
    model.objects.filter(pk=request.POST.get('link_id')).delete()
    messages.info(request, "Link removed.")


def room_links_view(request):
    """Link display buildings and rooms to their estate records.

    Suggestions are computed here and offered for confirmation; none is
    pre-selected, and nothing is ever linked automatically. `building_hint` on
    an O365 mailbox is a hint for grouping, never a link.
    """
    from room_schedules.models import Building as DisplayBuilding
    from room_schedules.models import Room as DisplayRoom

    # All locations as well: the suggestions draw on the whole estate, which a
    # location-restricted user must not see.
    if not (request.user.has_perm(LINK_PERMISSION)
            and sees_all_locations(request)):
        raise PermissionDenied

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'link_building':
            _link_building(request)
        elif action == 'link_room':
            _link_room(request)
        elif action == 'unlink':
            _unlink(request)
        return redirect(reverse('admin:estate_room_links'))

    estate_buildings = list(
        Building.objects.select_related('campus').order_by('campus__name', 'name'))

    # Every existing link, fetched once and indexed, rather than one query per
    # row. The page lists every display building and room on the system, so a
    # per-row lookup would grow with the estate.
    building_links = {
        link.display_building_id: link
        for link in BuildingLink.objects.select_related(
            'estate_building', 'estate_building__campus')
    }
    room_links = {
        link.display_room_id: link
        for link in RoomLink.objects.select_related(
            'estate_room', 'estate_room__building')
    }

    buildings = []
    for display in DisplayBuilding.objects.order_by('name'):
        link = building_links.get(display.pk)
        buildings.append({
            'display': display,
            'link': link,
            'suggestions': [] if link else suggest_buildings(
                display.name, estate_buildings),
        })

    linked_estate_ids = {
        b['link'].estate_building_id for b in buildings if b['link']}

    # Candidate rooms per linked estate building, also fetched in one query and
    # grouped in Python.
    candidates_by_building = defaultdict(list)
    if linked_estate_ids:
        for room in Room.objects.filter(
                building_id__in=linked_estate_ids).order_by('name'):
            candidates_by_building[room.building_id].append(room)

    # Only display buildings that are already linked can offer room
    # suggestions, so unlinked ones are listed without a room section rather
    # than with a useless one.
    display_rooms = list(
        DisplayRoom.objects.select_related('building').order_by(
            'building__name', 'name'))
    room_groups = []
    for display_building, rooms in groupby(
            display_rooms, key=lambda r: r.building):
        link = building_links.get(display_building.pk)
        candidates = (
            candidates_by_building.get(link.estate_building_id, [])
            if link else [])
        entries = []
        for room in rooms:
            room_link = room_links.get(room.pk)
            entries.append({
                'display': room,
                'link': room_link,
                'suggestions': [] if (room_link or not candidates) else suggest_rooms(
                    room.label, candidates),
            })
        room_groups.append({
            'building': display_building,
            'estate_building': link.estate_building if link else None,
            'candidates': candidates,
            'rooms': entries,
        })

    context = {
        **admin.site.each_context(request),
        **_tab_context(),
        'title': 'Link display rooms to the estate directory',
        'opts': DisplayRoom._meta,
        'active_tab': 'estate',
        'buildings': buildings,
        'estate_buildings': estate_buildings,
        'room_groups': room_groups,
        'unlinked_building_count': sum(1 for b in buildings if not b['link']),
        'linked_building_count': len(linked_estate_ids),
    }
    return TemplateResponse(request, 'admin/estate/room_links.html', context)
