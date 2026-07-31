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

from django.contrib.auth.models import Permission, User
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
        Screen, Source, Team, TeamMembership,
    )
    from room_schedules.models import (
        Building, Event, IpAddress, O365Room, Room, RoomGroup,
    )

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
        interspersed_source=logo,
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
    # Fixed last_seen values, so the dashboard's online/offline split and the
    # offline watchlist look the same on every capture run.
    screen_specs = [
        ('Riverside Library — Foyer', '10.0.10.11', schedule, datetime.timedelta(seconds=5)),
        ('Riverside Library — Level 2', '10.0.10.12', schedule, datetime.timedelta(seconds=12)),
        ('Kelvin Building — Entrance', '10.0.20.11', science_schedule, datetime.timedelta(seconds=8)),
        ('Kelvin Building — Cafe', '10.0.20.12', science_schedule, datetime.timedelta(hours=6)),
        ('Sports Centre — Reception', '10.0.30.11', schedule, datetime.timedelta(days=3)),
    ]
    screens = []
    for name, ip, sched, ago in screen_specs:
        screen = Screen.objects.create(name=name, ip=ip, schedule=sched)
        screen.teams.add(demo_team)
        # last_seen is auto_now_add, so it has to be set after creation.
        Screen.objects.filter(pk=screen.pk).update(last_seen=now - ago)
        screens.append(screen)

    ticker_screen = screens[0]
    ticker_screen.ticker_enabled = True
    ticker_screen.ticker_text = (
        'Library open until 22:00 all week  •  Level 3 closed for maintenance '
        'on Thursday  •  Ask at the desk for help finding anything'
    )
    ticker_screen.interspersed_source = logo
    ticker_screen.save()

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
        'screen_id': ticker_screen.pk,
        'room_id': rooms[1].pk,
        'building_id': building.pk,
        'bookable_room_id': rooms[2].pk,
        'group_id': group.pk,
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
    ]
    for name, task, schedule in crontab_tasks:
        PeriodicTask.objects.get_or_create(
            name=name, defaults={'task': task, 'crontab': schedule},
        )
