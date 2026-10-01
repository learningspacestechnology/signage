"""Build an invented dataset for documentation screenshots.

Everything here is fictional — "Demo Team", "Riverside Library",
``@demo.invalid`` addresses — so committed screenshots never carry a real
username, room name or mailbox into the repository.

Room bookings are seeded **relative to now**, and the demo building's grid hours
are widened to bracket the current time, so a capture run produces a
sensible-looking grid whatever time of day it happens at. The room views only
return events ending in the future, so fixed clock times would leave the grid
empty for anyone capturing in the afternoon.
"""
import datetime
import io

from django.contrib.auth.models import Group, Permission, User
from django.core.files.base import ContentFile
from django.utils import timezone

from PIL import Image, ImageDraw

DEMO_TEAM = 'Demo Team'
OTHER_TEAM = 'Estates'

ADMIN_USERNAME = 'demo_admin'
OPERATOR_USERNAME = 'demo_operator'

# Palette for the generated placeholder posters — muted, so they read as
# "example content" rather than competing with the interface around them.
POSTER_COLOURS = [
    ((37, 99, 235), 'Welcome Week'),
    ((13, 148, 136), 'Library Opening Hours'),
    ((217, 119, 6), 'Careers Fair'),
    ((124, 58, 237), 'Exhibition: Coastlines'),
    ((190, 24, 93), 'Wellbeing Drop-in'),
    ((5, 150, 105), 'Cycle to Work'),
]


def _poster(colour, label, size=(960, 540)):
    """A plain captioned rectangle, so screenshots need no real artwork."""
    image = Image.new('RGB', size, colour)
    draw = ImageDraw.Draw(image)
    draw.rectangle([(24, 24), (size[0] - 24, size[1] - 24)], outline=(255, 255, 255), width=3)
    draw.text((48, size[1] // 2 - 8), label, fill=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return ContentFile(buffer.getvalue(), name=f'{label.lower().replace(" ", "-")}.png')


def _grant(user, *specs):
    """Grant permissions given as 'app_label.codename' strings."""
    for spec in specs:
        app_label, codename = spec.split('.')
        permission = Permission.objects.filter(
            content_type__app_label=app_label, codename=codename
        ).first()
        if permission:
            user.user_permissions.add(permission)


def _grant_model_perms(user, app_label, *models, actions=('view', 'add', 'change')):
    for model in models:
        for action in actions:
            _grant(user, f'{app_label}.{action}_{model}')


def seed():
    """Populate the current database. Returns ids the shot specs interpolate."""
    from screens.models import (
        Playlist, PlaylistEntry, PlaylistRelation, Schedule, ScheduleRule,
        Screen, ScreenStatus, ScreenStatusEvent, Source, Team, TeamMembership,
    )
    from room_schedules.models import (
        Building, Event, IpAddress, O365Room, Room, RoomGroup,
    )
    # Aliased: both apps have a Building and a Room, and they mean different
    # things — display configuration versus the University's own record.
    from estate.models import Building as EstateBuilding
    from estate.models import BuildingLink
    from estate.models import Campus as EstateCampus
    from estate.models import LocationGroup, LocationGroupMembership
    from estate.models import Room as EstateRoom
    from estate.models import RoomLink
    from estate.location_scope import ALL_LOCATIONS_GROUP_NAME

    now = timezone.now()

    # ---- Teams and users ------------------------------------------------
    demo_team = Team.objects.create(name=DEMO_TEAM)
    other_team = Team.objects.create(name=OTHER_TEAM)

    admin = User.objects.create_superuser(
        ADMIN_USERNAME, 'demo.admin@demo.invalid', 'not-a-real-password',
        first_name='Alex', last_name='Doyle',
    )
    operator = User.objects.create_user(
        OPERATOR_USERNAME, 'demo.operator@demo.invalid', 'not-a-real-password',
        first_name='Sam', last_name='Reid', is_staff=True,
    )
    TeamMembership.objects.create(user=admin, team=demo_team)
    TeamMembership.objects.create(user=operator, team=demo_team)

    _grant_model_perms(
        operator, 'screens',
        'source', 'playlist', 'playlistentry', 'schedule', 'schedulerule', 'screen',
    )
    _grant_model_perms(
        operator, 'room_schedules', 'building', 'room', 'roomgroup', 'ipaddress',
    )
    _grant(operator, 'screens.change_ticker_text')

    # Every staff account that predates location groups was put in "All
    # locations" by estate migration 0005; the operator stands in for one.
    # Without it the screen list, dashboard and screen form capture empty.
    all_locations, _ = Group.objects.get_or_create(name=ALL_LOCATIONS_GROUP_NAME)
    all_locations.permissions.add(Permission.objects.get(
        content_type__app_label='estate', codename='access_all_locations'))
    operator.groups.add(all_locations)

    # Limited to a location group (seeded with the estate below), so the Users
    # list's Locations column shows something other than "All locations".
    facilities = User.objects.create_user(
        'demo_facilities', 'demo.facilities@demo.invalid', 'not-a-real-password',
        first_name='Jo', last_name='Kerr', is_staff=True,
    )
    TeamMembership.objects.create(user=facilities, team=demo_team)

    # ---- Content ---------------------------------------------------------
    sources = []
    for index, (colour, label) in enumerate(POSTER_COLOURS):
        source = Source.objects.create(
            type=Source.IMAGE,
            name=label,
            file=_poster(colour, label),
            created_by=operator if index % 2 else admin,
        )
        source.teams.add(demo_team)
        sources.append(source)

    # One of each remaining type so the "Content by type" chart has three slices.
    website = Source.objects.create(
        type=Source.IFRAME,
        name='Live departures board',
        url='https://example.invalid/departures',
        created_by=operator,
    )
    website.teams.add(demo_team)

    video = Source.objects.create(
        type=Source.VIDEO,
        name='Campus tour (clip)',
        # Not a playable file — it exists so the list row and type badge render.
        file=ContentFile(b'\x00\x00\x00\x18ftypmp42', name='campus-tour.mp4'),
        created_by=admin,
    )
    video.teams.add(demo_team)

    expiring = Source.objects.create(
        type=Source.IMAGE,
        name='Graduation ceremony — expires after the event',
        file=_poster((30, 64, 175), 'Graduation'),
        valid_from=now - datetime.timedelta(days=2),
        expires_at=now + datetime.timedelta(days=12),
        created_by=operator,
    )
    expiring.teams.add(demo_team)

    logo = Source.objects.create(
        type=Source.IMAGE,
        name='Institution logo (interspersed)',
        file=_poster((15, 23, 42), 'Logo'),
        created_by=admin,
    )
    logo.teams.add(demo_team)

    # ---- Playlists -------------------------------------------------------
    logo_playlist = Playlist.objects.create(
        name='Institution Branding',
        description='Mixed in between other playlists\' entries. Kept short so '
                    'it flashes past rather than taking a turn.',
        default_duration=4,
    )
    logo_playlist.teams.add(demo_team)
    PlaylistEntry.objects.create(playlist=logo_playlist, number=10, source=logo)

    campus_wide = Playlist.objects.create(
        name='Campus Wide Notices',
        description='Shown on every screen. Keep this short — it is inherited '
                    'by every other playlist.',
        default_duration=12,
    )
    campus_wide.teams.add(demo_team)

    library = Playlist.objects.create(
        name='Riverside Library Foyer',
        description='Library-specific content, plus everything from Campus Wide '
                    'Notices.',
        default_duration=10,
        interspersed_playlist=logo_playlist,
        interspersed_rate=2,
    )
    library.teams.add(demo_team)

    science = Playlist.objects.create(
        name='Kelvin Building Entrance',
        description='Science faculty screens.',
        default_duration=15,
    )
    science.teams.add(demo_team)

    for number, source in enumerate(sources[:2], start=1):
        PlaylistEntry.objects.create(
            playlist=campus_wide, source=source, number=number * 10,
        )
    for number, source in enumerate(sources[2:5], start=1):
        PlaylistEntry.objects.create(
            playlist=library, source=source, number=number * 10,
            duration=20 if number == 1 else None,
        )
    PlaylistEntry.objects.create(playlist=library, source=expiring, number=40)
    PlaylistEntry.objects.create(playlist=science, source=sources[5], number=10)
    PlaylistEntry.objects.create(playlist=science, source=website, number=20, duration=30)

    # Both faculty playlists inherit the shared notices — this is what makes the
    # Playlist Tree worth a screenshot.
    PlaylistRelation.objects.create(super_list=campus_wide, inheriting_list=library)
    PlaylistRelation.objects.create(super_list=campus_wide, inheriting_list=science)

    # ---- Schedules -------------------------------------------------------
    schedule = Schedule.objects.create(
        name='Riverside Library',
        description='Standard library screen schedule.',
        default_playlist=library,
    )
    schedule.teams.add(demo_team)

    ScheduleRule.objects.create(
        schedule=schedule,
        playlist=campus_wide,
        starts=(now - datetime.timedelta(days=7)).date(),
        occurrences='RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR',
        start_time=datetime.time(9, 0),
        end_time=datetime.time(11, 0),
        priority=10,
    )

    science_schedule = Schedule.objects.create(
        name='Kelvin Building',
        description='Science faculty screens.',
        default_playlist=science,
    )
    science_schedule.teams.add(demo_team)

    # ---- Screens ---------------------------------------------------------
    # Fixed last_seen values, so the dashboard's status split and the watchlist
    # look the same on every capture run. `ping_ago` is how long since a
    # successful probe, or None for a screen that was probed and did not answer;
    # between them the specs below cover all three states, so no screenshot
    # shows a two-colour version of a three-colour feature.
    screen_specs = [
        ('Riverside Library — Foyer', '10.0.10.11', schedule,
         datetime.timedelta(seconds=5), None),
        ('Riverside Library — Level 2', '10.0.10.12', schedule,
         datetime.timedelta(seconds=12), None),
        ('Kelvin Building — Entrance', '10.0.20.11', science_schedule,
         datetime.timedelta(seconds=8), None),
        # Amber: alive on the network, but its player has stopped.
        ('Kelvin Building — Cafe', '10.0.20.12', science_schedule,
         datetime.timedelta(hours=6), datetime.timedelta(minutes=2)),
        # Red: probed, and nothing came back.
        ('Sports Centre — Reception', '10.0.30.11', schedule,
         datetime.timedelta(days=3), None),
    ]
    screens = []
    for name, ip, sched, ago, ping_ago in screen_specs:
        screen = Screen.objects.create(name=name, ip=ip, schedule=sched)
        screen.teams.add(demo_team)
        # last_seen is auto_now_add, so it has to be set after creation.
        Screen.objects.filter(pk=screen.pk).update(
            last_seen=now - ago,
            # Only the non-reporting screens are ever probed, matching what
            # check_screens actually does.
            last_ping_ok=now - ping_ago if ping_ago else None,
            last_ping_attempt=(
                now - datetime.timedelta(minutes=2)
                if ago > datetime.timedelta(minutes=1) else None),
        )
        screens.append(screen)

    # A little history, so the screen page's Status panel and the "since"
    # labels are not empty in captures.
    #
    # The transition into a screen's current state is stamped at its last
    # check-in, since that is the moment it stopped reporting -- otherwise the
    # captured "since 7 hours ago" would sit next to a "last seen 3 days ago"
    # and read as a contradiction. Written oldest first, matching the order
    # check_screens appends in and the assumption cleanup_status_events makes
    # when it picks out each screen's latest row.
    for (_name, _ip, _sched, ago, _ping_ago), screen in zip(screen_specs, screens):
        screen.refresh_from_db()
        status, reason = screen.status_and_reason()
        if status == ScreenStatus.ONLINE:
            ScreenStatusEvent.objects.create(
                screen=screen, status=status, reason=reason,
                at=now - datetime.timedelta(hours=7))
            continue
        ScreenStatusEvent.objects.create(
            screen=screen, status=ScreenStatus.ONLINE, reason='',
            at=now - ago - datetime.timedelta(hours=2))
        ScreenStatusEvent.objects.create(
            screen=screen, status=status, reason=reason, at=now - ago)

    ticker_screen = screens[0]
    ticker_screen.ticker_enabled = True
    ticker_screen.ticker_text = (
        'Library open until 22:00 all week  •  Level 3 closed for maintenance '
        'on Thursday  •  Ask at the desk for help finding anything'
    )
    ticker_screen.save()

    # Screen-level interspersed content goes on a screen *without* a ticker:
    # the two are mutually exclusive, and the screen-form screenshot needs a
    # form where the fields are actually shown.
    interspersed_screen = screens[1]
    interspersed_screen.interspersed_playlist = logo_playlist
    interspersed_screen.interspersed_rate = 3
    interspersed_screen.save()

    # A second team's screen, so the team switcher demonstrably filters.
    other_playlist = Playlist.objects.create(name='Estates Notices', default_duration=10)
    other_playlist.teams.add(other_team)
    other_schedule = Schedule.objects.create(
        name='Estates', default_playlist=other_playlist,
    )
    other_schedule.teams.add(other_team)
    estates_screen = Screen.objects.create(
        name='Estates Office', ip='10.0.40.11', schedule=other_schedule,
    )
    estates_screen.teams.add(other_team)

    # ---- Buildings, rooms and groups -------------------------------------
    # Bracket "now" so the grid always has usable hours on it.
    start_hour = max(0, min(now.hour - 1, 16))
    building = Building.objects.create(
        name='Riverside Library',
        default_display=Building.DISPLAY_GRID,
        grid_start_hour=start_hour,
        grid_end_hour=min(24, start_hour + 8),
        pagination_duration_seconds=20,
        screensaver_enabled=False,
    )
    kelvin = Building.objects.create(
        name='Kelvin Building',
        default_display=Building.DISPLAY_FOYER,
        grid_start_hour=start_hour,
        grid_end_hour=min(24, start_hour + 8),
    )

    room_specs = [
        ('Seminar Room 1.01', 'Seminar Room 1', 'seminar-1.01@demo.invalid', False),
        ('Seminar Room 1.02', 'Seminar Room 2', 'seminar-1.02@demo.invalid', True),
        ('Group Study 2.14', 'Group Study Room', 'study-2.14@demo.invalid', True),
        ('Lecture Theatre A', '', 'theatre-a@demo.invalid', False),
    ]
    rooms = []
    for name, display_name, email, bookable in room_specs:
        rooms.append(Room.objects.create(
            name=name,
            display_name=display_name,
            building=building,
            o365_calendar_email=email,
            allow_booking=bookable,
            pagination_duration_seconds=60,
            screensaver_enabled=True,
            screensaver_duration_seconds=5,
        ))

    kelvin_room = Room.objects.create(
        name='Physics Meeting Room',
        building=kelvin,
        o365_calendar_email='physics-meeting@demo.invalid',
        allow_booking=False,
    )

    group = RoomGroup.objects.create(
        name='Ground Floor Seminar Rooms',
        building=building,
        default_display=RoomGroup.DISPLAY_GRID,
        grid_start_hour=start_hour,
        grid_end_hour=min(24, start_hour + 8),
    )
    group.rooms.set(rooms[:2])

    IpAddress.objects.create(ip_address='10.0.50.11', room=rooms[1])
    IpAddress.objects.create(ip_address='10.0.50.20', building=building)
    IpAddress.objects.create(ip_address='10.0.50.30', room_group=group)

    # ---- Estate directory ------------------------------------------------
    # A stand-in for what the nightly Learning Spaces sync would have written,
    # created directly rather than through estate.sync so no capture run can
    # reach the real datastore. Names match the display buildings above so the
    # linking page has something plausible to suggest.
    estate_campus = EstateCampus.objects.create(
        name='Riverside Campus', code='RC')
    estate_library = EstateBuilding.objects.create(
        key="RVL", name='Riverside Library', campus=estate_campus)
    estate_kelvin = EstateBuilding.objects.create(
        key="KLV", name='Kelvin Building', campus=estate_campus)
    # No screens in this one, so the estate lists show a building at zero and
    # the changelist filters demonstrably leave it out.
    EstateBuilding.objects.create(
        key="SPC", name='Sports Centre', campus=estate_campus)

    # Sparse on purpose: the real feed leaves capacity, support, codes and
    # location blank on a good share of rooms, and the pages must read
    # correctly when they are. Two library rooms are inactive — one holding a
    # screen, one without — so the Inactive badge appears on the screen list
    # and in both halves of the per-building page.
    estate_room_specs = [
        # id, name, building, capacity, room_status, building_code, active
        ('RVL-0101', 'Seminar Room 1.01', estate_library, 24,
         'General Teaching', '0501', True),
        ('RVL-0102', 'Seminar Room 1.02', estate_library, 24,
         'General Teaching', '0501', True),
        ('RVL-0214', 'Group Study 2.14', estate_library, 8,
         'Student Study Space', '0501', False),
        ('RVL-FOYR', 'Library Foyer', estate_library, None,
         'Specialist', '', True),
        # Left with no screen, so the per-building page's "rooms with no
        # screen" panel is not empty in the capture.
        ('RVL-0301', 'Reading Room 3.01', estate_library, 60,
         'Student Study Space', '0501', False),
        ('KLV-ENTR', 'Kelvin Entrance', estate_kelvin, None,
         'Specialist', '0612', True),
        ('KLV-CAFE', 'Kelvin Cafe', estate_kelvin, 40, 'Specialist', '0612', True),
        ('KLV-PMR', 'Physics Meeting Room', estate_kelvin, 12,
         'Meeting Space', '0612', True),
    ]
    estate_rooms = {}
    for lsd_id, name, est_building, capacity, status, code, active in estate_room_specs:
        supported = capacity is not None
        estate_rooms[lsd_id] = EstateRoom.objects.create(
            lsd_id=lsd_id, name=name, building=est_building,
            capacity=capacity, room_status=status, active=active,
            building_code=code,
            public_campus='Central' if est_building is estate_library else '',
            optime_index=500 + len(estate_rooms) if status == 'General Teaching' else None,
            support_type='Central' if supported else '',
            service_provider='Demo AV' if supported else '',
            voip_number=505000 + len(estate_rooms) if supported else None,
            last_seen_at=now,
        )

    # Most demo screens get a room; the Sports Centre one is deliberately left
    # without, so the "No room set" filter and the dashboard's unassigned line
    # both have something to report.
    screen_rooms = {
        'Riverside Library — Foyer': 'RVL-FOYR',
        'Riverside Library — Level 2': 'RVL-0214',
        'Kelvin Building — Entrance': 'KLV-ENTR',
        'Kelvin Building — Cafe': 'KLV-CAFE',
    }
    for screen in screens:
        lsd_id = screen_rooms.get(screen.name)
        if lsd_id:
            Screen.objects.filter(pk=screen.pk).update(
                room=estate_rooms[lsd_id])

    # A whole building plus one room elsewhere, so the form shows both kinds
    # of grant and the list's summary reads "1 building, 1 room".
    location_group = LocationGroup.objects.create(
        name='Kelvin Building and library foyer',
        description='Facilities team: the Kelvin screens and the library '
                    'foyer display.')
    location_group.buildings.add(estate_kelvin)
    location_group.rooms.add(estate_rooms['RVL-FOYR'])
    LocationGroupMembership.objects.create(user=facilities, group=location_group)

    # One link already made and one left open, so the linking page shows both
    # states rather than only the empty one.
    BuildingLink.objects.create(
        display_building=building, estate_building=estate_library)
    RoomLink.objects.create(
        display_room=rooms[0], estate_room=estate_rooms['RVL-0101'])

    # ---- Bookings --------------------------------------------------------
    # Relative to now so every room reads as intended at capture time:
    #   rooms[0] busy, rooms[1] free but starting soon, rooms[2] free and
    #   bookable, rooms[3] free with a later booking.
    booking_specs = [
        (rooms[0], 'Research Methods Seminar', 'Dr J. Whitfield', -30, 60, 'normal'),
        (rooms[1], 'Undergraduate Tutorial', 'Dr P. Okafor', 10, 70, 'normal'),
        (rooms[2], 'Project Catch-up', 'M. Lindqvist', 180, 240, 'normal'),
        (rooms[3], 'Guest Lecture: Coastal Erosion', 'Prof R. Adeyemi', 45, 165, 'normal'),
        (rooms[3], 'Staff One-to-One', 'K. Bergstrom', 200, 230, 'private'),
        (kelvin_room, 'Group Meeting', 'S. Nakamura', 20, 80, 'normal'),
    ]
    for index, (room, name, organiser, start_min, end_min, sensitivity) in enumerate(booking_specs):
        Event.objects.create(
            name=name,
            room=room,
            organiser=organiser,
            start_time=now + datetime.timedelta(minutes=start_min),
            end_time=now + datetime.timedelta(minutes=end_min),
            o365_event_id=f'demo-event-{index}',
            sensitivity=sensitivity,
        )

    # ---- O365 inventory --------------------------------------------------
    for room in rooms + [kelvin_room]:
        O365Room.objects.create(
            email=room.o365_calendar_email,
            name=room.name,
            building_hint=room.building.name,
        )
    for name, hint in [
        ('Seminar Room 3.05', 'Riverside Library'),
        ('Quiet Study 3.06', 'Riverside Library'),
        ('Chemistry Meeting Room', 'Kelvin Building'),
        ('Boardroom', ''),
    ]:
        O365Room.objects.create(
            email=f'{name.lower().replace(" ", "-").replace(".", "-")}@demo.invalid',
            name=name,
            building_hint=hint,
        )
    O365Room.objects.create(
        email='av-store@demo.invalid', name='AV Store',
        building_hint='Riverside Library', no_calendar_access=True,
    )
    # Flags an assigned room, which is what puts it on the "missing" list.
    O365Room.objects.filter(email=kelvin_room.o365_calendar_email).update(
        missing_from_tenant=True,
    )

    _seed_periodic_tasks()

    return {
        'playlist_id': library.pk,
        'schedule_id': schedule.pk,
        'screen_id': interspersed_screen.pk,
        'ticker_screen_id': ticker_screen.pk,
        'room_id': rooms[1].pk,
        'building_id': building.pk,
        'bookable_room_id': rooms[2].pk,
        'group_id': group.pk,
        'estate_building_id': estate_library.pk,
        'estate_room_id': estate_rooms['RVL-0101'].pk,
        'location_group_id': location_group.pk,
    }


def _seed_periodic_tasks():
    """Mirror CELERY_BEAT_SCHEDULE into the database scheduler.

    In production beat uses the database scheduler, so these rows are what an
    administrator actually sees and edits. Without them the Periodic Tasks
    screenshot would be an empty list.
    """
    from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask

    every_5_min, _ = IntervalSchedule.objects.get_or_create(
        every=5, period=IntervalSchedule.MINUTES,
    )
    hourly, _ = CrontabSchedule.objects.get_or_create(
        minute='1', hour='*', day_of_week='*', day_of_month='*', month_of_year='*',
    )
    midnight, _ = CrontabSchedule.objects.get_or_create(
        minute='0', hour='0', day_of_week='*', day_of_month='*', month_of_year='*',
    )
    early, _ = CrontabSchedule.objects.get_or_create(
        minute='15', hour='2', day_of_week='*', day_of_month='*', month_of_year='*',
    )
    early_estate, _ = CrontabSchedule.objects.get_or_create(
        minute='45', hour='2', day_of_week='*', day_of_month='*', month_of_year='*',
    )

    interval_tasks = [
        ('Clean up expired content', 'screens.tasks.cleanup_sources'),
        ('Update playlists', 'screens.tasks.update_playlists'),
        ('Clean up expired schedule rules', 'screens.tasks.cleanup_schedule'),
    ]
    for name, task in interval_tasks:
        PeriodicTask.objects.get_or_create(
            name=name, defaults={'task': task, 'interval': every_5_min},
        )

    crontab_tasks = [
        ('Pull room bookings', 'room_schedules.tasks.build_schedule', hourly),
        ('Clean up old events', 'room_schedules.tasks.cleanup_schedule', midnight),
        ('Sync O365 rooms', 'room_schedules.tasks.sync_o365_rooms', early),
        ('Sync estate', 'estate.tasks.sync_estate', early_estate),
    ]
    for name, task, schedule in crontab_tasks:
        PeriodicTask.objects.get_or_create(
            name=name, defaults={'task': task, 'crontab': schedule},
        )
