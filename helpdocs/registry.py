"""The help documentation manifest.

Structure and ordering live here. Page *titles* deliberately do not — each page's
title is the first `# ` heading in its markdown file, so there is exactly one
place to change it. `manage.py check_help_docs` validates this manifest against
what is actually on disk.

Adding a page: drop `content/<audience>/<slug>.md` in place and add a `Page(...)`
entry below, in the section you want it to appear under.
"""
from dataclasses import dataclass, field
from pathlib import Path

from django.urls import reverse

USERS = 'users'
TECHNICAL = 'technical'

AUDIENCES = (USERS, TECHNICAL)

#: Short label used in navigation and page headers.
AUDIENCE_LABELS = {
    USERS: 'Help & Tutorials',
    TECHNICAL: 'Technical Documentation',
}

#: Material Symbols icon name, matching the sidebar entries.
AUDIENCE_ICONS = {
    USERS: 'help',
    TECHNICAL: 'menu_book',
}

#: Permission required to read an audience. ``None`` means "any signed-in user".
AUDIENCE_PERMISSIONS = {
    USERS: None,
    TECHNICAL: 'helpdocs.view_technical_docs',
}

#: Section headings, in display order, per audience.
SECTION_ORDER = {
    USERS: (
        'Start here',
        'Content',
        'Playlists',
        'Scheduling & screens',
        'Day to day',
    ),
    TECHNICAL: (
        'Access & accounts',
        'Displays & devices',
        'Room integration',
        'Operations',
    ),
}

CONTENT_ROOT = Path(__file__).resolve().parent / 'content'


@dataclass(frozen=True)
class Page:
    audience: str
    slug: str
    section: str
    summary: str
    #: Admin URL names this page is the help for. Drives the contextual "?"
    #: link injected above changelists and change forms.
    admin_url_names: tuple = field(default=())
    #: Permissions required *in addition to* the audience gate, as
    #: 'app_label.codename'. Empty means "anyone who can read this audience".
    #: These mirror the sidebar's own permission lambdas, so a page about a
    #: screen the reader cannot open never appears.
    permissions: tuple = field(default=())
    #: By default holding *any* of `permissions` is enough — the useful case is
    #: "can view or add content". Set True to require all of them.
    require_all: bool = False

    @property
    def path(self) -> Path:
        return CONTENT_ROOT / self.audience / f'{self.slug}.md'

    @property
    def url(self) -> str:
        return reverse(
            'admin:help_page',
            kwargs={'audience': self.audience, 'slug': self.slug},
        )

    @property
    def permission(self):
        return AUDIENCE_PERMISSIONS[self.audience]


PAGES = (
    # ---------------------------------------------------------------- users ---
    Page(
        audience=USERS, slug='getting-started', section='Start here',
        summary='Signing in, finding your way around, and the first five things to do.',
    ),
    Page(
        audience=USERS, slug='concepts', section='Start here',
        summary='How content, playlists, schedules and screens fit together. '
                'Read this once and everything else makes sense.',
    ),
    Page(
        audience=USERS, slug='content', section='Content',
        summary='Adding images, videos and web pages; scheduling when they start '
                'and stop; what to do when an upload is rejected.',
        admin_url_names=(
            'screens_source_changelist',
            'screens_source_change',
            'screens_source_add',
        ),
        permissions=('screens.view_source',),
    ),
    Page(
        audience=USERS, slug='content-bulk-upload', section='Content',
        summary='Uploading many files at once and dropping them straight into playlists.',
        admin_url_names=('screens_source_bulk_create',),
        permissions=('screens.add_source',),
    ),
    Page(
        audience=USERS, slug='playlists', section='Playlists',
        summary='Building a playlist, ordering entries, setting how long each one '
                'shows, and adding a logo between every slide.',
        admin_url_names=(
            'screens_playlist_changelist',
            'screens_playlist_change',
            'screens_playlist_add',
        ),
        permissions=('screens.view_playlist',),
    ),
    Page(
        audience=USERS, slug='playlist-inheritance', section='Playlists',
        summary='Sharing content between playlists without duplicating it, and '
                'reading the Playlist Tree.',
        admin_url_names=('screens_playlist_tree',),
        permissions=('screens.view_playlist',),
    ),
    Page(
        audience=USERS, slug='schedules', section='Scheduling & screens',
        summary='Deciding which playlist plays when, with recurring rules and priorities.',
        admin_url_names=(
            'screens_schedule_changelist',
            'screens_schedule_change',
            'screens_schedule_add',
        ),
        permissions=('screens.view_schedule',),
    ),
    Page(
        audience=USERS, slug='screens', section='Scheduling & screens',
        summary='Adding a screen, previewing what it shows, and understanding '
                'Online vs Offline.',
        admin_url_names=(
            'screens_screen_changelist',
            'screens_screen_change',
            'screens_screen_add',
        ),
        permissions=('screens.view_screen',),
    ),
    Page(
        audience=USERS, slug='ticker-tape', section='Scheduling & screens',
        summary='Putting a scrolling message along the bottom of a screen.',
        permissions=('screens.view_screen',),
    ),
    Page(
        audience=USERS, slug='dashboard', section='Day to day',
        summary='Reading the overview dashboard and spotting a screen that has '
                'dropped offline.',
        admin_url_names=('index',),
    ),
    Page(
        audience=USERS, slug='teams', section='Day to day',
        summary='Why you only see some content, and how to switch between teams.',
    ),
    Page(
        audience=USERS, slug='troubleshooting', section='Day to day',
        summary="Something isn't showing on a screen — start here.",
    ),

    # ------------------------------------------------------------ technical ---
    Page(
        audience=TECHNICAL, slug='access-model', section='Access & accounts',
        summary='Staff, superusers, Groups and Teams — which layer controls what, '
                'and how they compose.',
    ),
    Page(
        audience=TECHNICAL, slug='users-and-teams', section='Access & accounts',
        summary='Pre-provisioning accounts, granting permissions, and creating '
                'or retiring a team.',
        admin_url_names=(
            'auth_user_changelist', 'auth_user_change', 'auth_user_add',
            'auth_group_changelist', 'auth_group_change', 'auth_group_add',
            'screens_team_changelist', 'screens_team_change', 'screens_team_add',
        ),
        permissions=('auth.view_user', 'auth.view_group'),
    ),
    Page(
        audience=TECHNICAL, slug='sso-and-entra', section='Access & accounts',
        summary='How Microsoft sign-in works end to end, the two app '
                'registrations, and fixing a blocked account.',
    ),
    Page(
        audience=TECHNICAL, slug='device-commissioning', section='Displays & devices',
        summary='Getting a new display onto the system: finding its IP, '
                'registering it, and the access rules that gate it.',
    ),
    Page(
        audience=TECHNICAL, slug='player-api', section='Displays & devices',
        summary='The endpoints a display device calls, and how the heartbeat '
                'drives Online/Offline.',
    ),
    Page(
        audience=TECHNICAL, slug='room-displays', section='Room integration',
        summary='Room, building and room-group displays: choosing a layout, '
                'setting the hours shown, and naming rooms.',
        admin_url_names=(
            'room_schedules_building_changelist',
            'room_schedules_building_change',
            'room_schedules_building_add',
            'room_schedules_room_changelist',
            'room_schedules_room_change',
            'room_schedules_room_add',
            'room_schedules_roomgroup_changelist',
            'room_schedules_roomgroup_change',
            'room_schedules_roomgroup_add',
        ),
        permissions=(
            'room_schedules.view_building',
            'room_schedules.view_room',
            'room_schedules.view_roomgroup',
        ),
    ),
    Page(
        audience=TECHNICAL, slug='booking-a-room', section='Room integration',
        summary='Using Book Now on a room screen, and what the status light means.',
        permissions=('room_schedules.view_room',),
    ),
    Page(
        audience=TECHNICAL, slug='o365-rooms', section='Room integration',
        summary='Syncing the tenant room list, assigning mailboxes to buildings, '
                'and triaging rooms that stop working.',
        admin_url_names=(
            'room_schedules_o365_assigned',
            'room_schedules_o365_unassigned',
        ),
        permissions=('room_schedules.change_room',),
    ),
    Page(
        audience=TECHNICAL, slug='scheduled-tasks', section='Operations',
        summary='What runs in the background, when, and how to change or '
                'trigger it.',
        admin_url_names=(
            'django_celery_beat_periodictask_changelist',
            'django_celery_beat_periodictask_change',
            'django_celery_beat_periodictask_add',
            'django_celery_results_taskresult_changelist',
        ),
        permissions=('django_celery_beat.view_periodictask',),
    ),
    Page(
        audience=TECHNICAL, slug='config-only-settings', section='Operations',
        summary='Behaviour that has no screen in the admin, and what each '
                'setting changes.',
    ),
    Page(
        audience=TECHNICAL, slug='troubleshooting', section='Operations',
        summary='Startup failures, 403s on screen URLs, stale rooms and silent displays.',
    ),
)


def intro_path(audience: str) -> Path:
    """Markdown shown at the top of an audience's index page."""
    return CONTENT_ROOT / audience / 'index.md'


def can_read_audience(user, audience: str) -> bool:
    """Whether `user` may read `audience` at all. `user=None` means "no check"."""
    permission = AUDIENCE_PERMISSIONS.get(audience)
    if permission is None or user is None:
        return True
    return user.has_perm(permission)


def can_read_page(user, page: Page) -> bool:
    """Audience gate plus the page's own permissions.

    `user=None` means "don't filter" — used by check_help_docs and by the tests,
    which need to see every page regardless of who is asking.
    """
    if user is None:
        return True
    if not can_read_audience(user, page.audience):
        return False
    if not page.permissions:
        return True
    check = all if page.require_all else any
    return check(user.has_perm(p) for p in page.permissions)


def pages_for(audience: str, user=None):
    return tuple(
        p for p in PAGES
        if p.audience == audience and can_read_page(user, p)
    )


def get_page(audience: str, slug: str):
    for page in PAGES:
        if page.audience == audience and page.slug == slug:
            return page
    return None


def sections_for(audience: str, user=None):
    """[(section title, [Page, ...]), ...] in SECTION_ORDER order.

    Sections with no *visible* pages are dropped, so a reader never sees an
    empty heading. A page whose section is missing from SECTION_ORDER is
    appended at the end rather than silently hidden.
    """
    pages = pages_for(audience, user)
    ordered = list(SECTION_ORDER.get(audience, ()))
    for page in pages:
        if page.section not in ordered:
            ordered.append(page.section)

    grouped = []
    for section in ordered:
        in_section = [p for p in pages if p.section == section]
        if in_section:
            grouped.append((section, in_section))
    return grouped


def _build_admin_url_index():
    index = {}
    for page in PAGES:
        for url_name in page.admin_url_names:
            # First registration wins, so a user-facing page takes precedence
            # over a technical one if both ever claim the same admin view.
            index.setdefault(url_name, page)
    return index


ADMIN_URL_INDEX = _build_admin_url_index()


def page_for_admin_url_name(url_name):
    if not url_name:
        return None
    return ADMIN_URL_INDEX.get(url_name)
