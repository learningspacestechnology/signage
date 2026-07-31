"""Declarative screenshot specifications.

Each spec says which page to visit, as whom, and how to frame it.
``manage.py capture_help_screenshots`` walks this list; ``check_help_docs``
cross-references it against ``screenshot:`` references in the markdown, so a spec
with no reference (or a reference with no spec) is reported rather than silently
ignored.

``path`` may contain ``{placeholders}``, filled in from the ids returned by
``seed_help_demo_data`` — the demo database is rebuilt from scratch each run, so
primary keys are not stable enough to hardcode.
"""
from dataclasses import dataclass, field

#: Who the browser is signed in as for a shot.
ANONYMOUS = None
ADMIN = 'admin'          # superuser: sees Teams, ticker layout, "All teams"
OPERATOR = 'operator'    # staff, one team, normal model permissions

DEFAULT_VIEWPORT = (1440, 900)

#: Django admin change/add forms are ``<form id="<model>_form">``. Matching a
#: bare ``form`` instead picks up Unfold's hidden sidebar logout form, which
#: never becomes visible.
FORM = 'form[id$="_form"]'


@dataclass(frozen=True)
class Shot:
    name: str
    path: str
    #: ANONYMOUS / ADMIN / OPERATOR
    as_user: str = OPERATOR
    viewport: tuple = DEFAULT_VIEWPORT
    #: CSS selector to crop to. None captures the viewport.
    clip: str = None
    #: Selectors to click before capturing, in order (e.g. to open a fieldset).
    click: tuple = field(default=())
    #: Selector that must be present before capturing.
    wait_for: str = None
    #: Playwright wait state for `wait_for` — 'visible' or 'attached'.
    wait_state: str = 'visible'
    #: Extra settle time in ms for charts/animations.
    settle_ms: int = 350
    #: Capture the whole scrollable page rather than just the viewport.
    full_page: bool = False
    #: Fixed region to capture, as (x, y, width, height). Use instead of
    #: `clip` when the interesting area spills outside any one element —
    #: an open dropdown, for instance.
    clip_rect: tuple = None
    #: JavaScript run after load, before capture. For state that a click
    #: can't reliably reach.
    run_js: str = None


SHOTS = (
    # ---- Signing in ------------------------------------------------------
    Shot(
        name='login-page',
        path='/admin/login/',
        as_user=ANONYMOUS,
        # The password form ships hidden behind a toggle, so wait on the form
        # element by id rather than on its visibility.
        wait_for='#login-form',
        wait_state='attached',
    ),

    # ---- Dashboard -------------------------------------------------------
    Shot(
        name='dashboard',
        path='/admin/',
        # Charts animate in; give them a moment or they capture half-drawn.
        settle_ms=1200,
        full_page=True,
    ),
    Shot(
        name='team-switcher',
        path='/admin/',
        as_user=ADMIN,
        # Open the picker, then grab a band across the top: the dropdown is
        # absolutely positioned and spills outside the header element.
        click=('#header-inner button',),
        clip_rect=(0, 0, 1440, 300),
        settle_ms=700,
    ),

    # ---- Content ---------------------------------------------------------
    Shot(
        name='content-list',
        path='/admin/screens/source/',
        wait_for='#changelist',
    ),
    Shot(
        name='content-add',
        path='/admin/screens/source/add/',
        wait_for=FORM,
        full_page=True,
    ),
    Shot(
        name='bulk-upload',
        path='/admin/screens/source/bulk_create/',
        wait_for=FORM,
    ),

    # ---- Playlists -------------------------------------------------------
    Shot(
        name='playlist-entries',
        path='/admin/screens/playlist/{playlist_id}/change/',
        wait_for=FORM,
        full_page=True,
    ),
    Shot(
        name='playlist-tree',
        path='/admin/screens/playlist/tree/',
        # The force-directed layout needs to settle before it reads clearly.
        settle_ms=2500,
        wait_for='svg',
    ),

    # ---- Schedules -------------------------------------------------------
    Shot(
        name='schedule-form',
        path='/admin/screens/schedule/{schedule_id}/change/',
        wait_for=FORM,
        full_page=True,
    ),
    Shot(
        name='schedule-rule',
        path='/admin/screens/schedule/{schedule_id}/change/',
        wait_for=FORM,
        clip='#schedulerule_set-group',
        settle_ms=900,
    ),

    # ---- Screens ---------------------------------------------------------
    Shot(
        name='screen-form',
        path='/admin/screens/screen/{screen_id}/change/',
        wait_for=FORM,
        full_page=True,
    ),
    Shot(
        name='ticker-fieldset',
        path='/admin/screens/screen/{screen_id}/change/',
        as_user=ADMIN,
        wait_for=FORM,
        # The ticker fieldset ships collapsed. Depending on the Unfold version
        # that is either a <details> or Django's own collapse.js Show/Hide
        # toggle, so drive both rather than guessing which. The sticky submit
        # row is viewport-anchored and would otherwise sit across the middle of
        # an element screenshot.
        run_js=(
            "document.querySelectorAll('details').forEach(d => d.open = true);"
            "document.querySelectorAll('fieldset.collapse .collapse-toggle')"
            ".forEach(a => a.click());"
            "document.querySelectorAll('fieldset.collapse').forEach("
            "f => f.classList.remove('collapsed'));"
            "const row = document.getElementById('submit-row');"
            "if (row) { row.style.display = 'none'; }"
        ),
        clip='fieldset.collapse',
        settle_ms=600,
    ),

    # ---- Room displays ---------------------------------------------------
    Shot(
        name='room-form',
        path='/admin/room_schedules/room/{room_id}/change/',
        wait_for=FORM,
        full_page=True,
    ),
    Shot(
        name='building-grid',
        path='/event_schedules/{building_id}',
        as_user=ANONYMOUS,
        viewport=(1600, 900),
        settle_ms=900,
    ),
    Shot(
        name='book-now',
        path='/event_schedules/{building_id}/{bookable_room_id}',
        as_user=ANONYMOUS,
        # Room screens are built for portrait tablets, but a full-height capture
        # is mostly empty below the booking list.
        viewport=(1080, 900),
        settle_ms=900,
    ),

    # ---- Administration --------------------------------------------------
    Shot(
        name='user-add',
        path='/admin/auth/user/add/',
        as_user=ADMIN,
        wait_for=FORM,
        full_page=True,
    ),
    Shot(
        name='o365-assigned',
        path='/admin/room_schedules/o365_assigned/',
        as_user=ADMIN,
        full_page=True,
    ),
    Shot(
        name='o365-unassigned',
        path='/admin/room_schedules/o365_unassigned/',
        as_user=ADMIN,
        full_page=True,
    ),
    Shot(
        name='periodic-tasks',
        path='/admin/django_celery_beat/periodictask/',
        as_user=ADMIN,
        wait_for='#changelist',
    ),
)


def shot_names():
    return {shot.name for shot in SHOTS}


def get_shot(name):
    for shot in SHOTS:
        if shot.name == name:
            return shot
    return None
