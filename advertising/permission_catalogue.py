"""What the permission grid offers, in the sidebar's own words.

Django's permission picker lists every model permission in the project, 177 of
them, under names nobody here chose: "Can add source" for content, five Celery
models that match a search for "schedule", and `contenttypes` rows that sound
like content. And one real job usually needs several of them — editing a
playlist's entries checks `playlistentry` permissions, not `playlist` ones,
because Django checks each inline model on its own.

So the Group and User pages show this catalogue instead (rendered by
`advertising.permission_grid`). Each row is one area of the admin, named as the
sidebar names it. Each action on a row is a **bundle**: every permission that
action really needs, with the one that decides whether the cell shows as ticked
first.

Every permission in the database is either offered here or listed in ``HIDDEN``
with the reason it is not. `advertising/tests/test_permission_grid.py` fails
otherwise, so a new model has to be placed before the suite passes.

Pure data: no model imports, so anything may import it.
"""

from dataclasses import dataclass, field

VIEW, ADD, CHANGE, DELETE = 'view', 'add', 'change', 'delete'

#: Column order and headings. "Edit" rather than "Change": it is what the
#: buttons in the admin say.
ACTIONS = ((VIEW, 'View'), (ADD, 'Add'), (CHANGE, 'Edit'), (DELETE, 'Delete'))

#: Heading of the column after Delete, holding the single permissions (extras)
#: that no action covers.
EXTRAS_HEADING = 'Enabled'


def _perms(model, *actions):
    """``_perms('screens.playlist', 'add')`` -> ``('screens.add_playlist',)``."""
    app_label, name = model.split('.')
    return tuple(f'{app_label}.{action}_{name}' for action in actions)


def _all(model):
    return _perms(model, VIEW, ADD, CHANGE, DELETE)


@dataclass(frozen=True)
class Extra:
    """A single named permission, ticked on its own under its row."""

    key: str
    label: str
    description: str
    permissions: tuple


@dataclass(frozen=True)
class Row:
    key: str
    label: str
    description: str
    #: Action -> bundle. An action left out shows as "—" in the grid.
    actions: dict = field(default_factory=dict)
    #: Action -> cell keys ticked along with it, because the action does not
    #: work without them. View of the same row is implied separately.
    requires: dict = field(default_factory=dict)
    extras: tuple = ()
    #: Shown under the row: for actions that amount to administrator access.
    warning: str = ''


@dataclass(frozen=True)
class Section:
    title: str
    rows: tuple


def _model_rows(view, add, change, delete):
    return {VIEW: view, ADD: add, CHANGE: change, DELETE: delete}


def _with_children(parent, *children):
    """A model edited together with inline children, as one set of bundles.

    Adding the parent adds its first rows; editing it adds, changes and
    removes rows; viewing it shows them. Deleting needs only the parent's own
    permission — the children are not registered in the admin, so Django does
    not ask about them when it cascades.
    """
    return _model_rows(
        view=_perms(parent, VIEW) + sum((_perms(c, VIEW) for c in children), ()),
        add=_perms(parent, ADD) + sum((_perms(c, ADD) for c in children), ()),
        change=_perms(parent, CHANGE) + sum(
            (_perms(c, ADD, CHANGE, DELETE) for c in children), ()),
        delete=_perms(parent, DELETE),
    )


ESTATE_VIEW = 'estate:view'

SECTIONS = (
    Section('Screens & Playlists', (
        Row('content', 'Content',
            "Images, videos and web pages. Add also allows Bulk Upload.",
            actions=_model_rows(*((p,) for p in _all('screens.source')))),
        Row('playlists', 'Playlists',
            "Ordered lists of content, and which playlists they inherit "
            "from. Includes the Playlist Tree.",
            actions=_with_children('screens.playlist',
                                   'screens.playlistentry',
                                   'screens.playlistrelation')),
        Row('schedules', 'Schedules',
            "Which playlist a screen shows at what time. Not the system's "
            "background-task timetable: that is Periodic tasks, under Task "
            "Management.",
            actions=_with_children('screens.schedule', 'screens.schedulerule')),
        Row('screens', 'Screens',
            "The physical displays: name, schedule and location. Add and Edit "
            "include viewing the estate directory, which the room picker needs.",
            actions=_model_rows(*((p,) for p in _all('screens.screen'))),
            requires={ADD: (ESTATE_VIEW,), CHANGE: (ESTATE_VIEW,)},
            extras=(
                Extra('screens:ticker_settings',
                      "Ticker: turn it on and choose its layout",
                      "Not included in Edit.",
                      ('screens.change_ticker_settings',)),
                Extra('screens:ticker_text',
                      "Ticker: write and style the message",
                      "Not included in Edit.",
                      ('screens.change_ticker_text',)),
            )),
    )),
    Section('Estate directory', (
        Row('estate', 'Campuses, buildings and rooms',
            "The University's estate, refreshed nightly from the Learning "
            "Spaces Datastore. Read-only for everyone, superusers included. "
            "Users see only the places their location groups grant.",
            actions={VIEW: _perms('estate.room', VIEW)
                     + _perms('estate.building', VIEW)
                     + _perms('estate.campus', VIEW)},
            extras=(
                Extra('estate:all_locations', "See every location",
                      "Ignore location groups and see screens everywhere. "
                      "Usually given through the All locations group.",
                      ('estate.access_all_locations',)),
            )),
    )),
    Section('Room Schedules', (
        Row('display_buildings', 'Buildings',
            "Display buildings for the room-booking screens and their "
            "building-wide displays. Not the estate directory's buildings.",
            actions=_model_rows(
                view=_perms('room_schedules.building', VIEW)
                + _perms('room_schedules.ipaddress', VIEW)
                + _perms('estate.buildinglink', VIEW),
                add=_perms('room_schedules.building', ADD)
                + _perms('room_schedules.ipaddress', ADD),
                change=_perms('room_schedules.building', CHANGE)
                + _perms('room_schedules.ipaddress', ADD, CHANGE, DELETE)
                + _perms('estate.buildinglink', CHANGE, DELETE),
                # Deleting a building deletes its link too, and Django asks
                # for permission on every registered model a delete cascades to.
                delete=_perms('room_schedules.building', DELETE)
                + _perms('estate.buildinglink', DELETE),
            ),
            # The building's rooms and room groups go with it.
            requires={DELETE: ('display_rooms:delete', 'room_groups:delete')}),
        Row('display_rooms', 'Rooms',
            "Display rooms and their O365 calendars. Edit also opens the O365 "
            "rooms pages, and Link display rooms for anyone who sees every "
            "location.",
            actions=_model_rows(
                view=_perms('room_schedules.room', VIEW)
                + _perms('room_schedules.ipaddress', VIEW)
                + _perms('estate.roomlink', VIEW),
                add=_perms('room_schedules.room', ADD)
                + _perms('room_schedules.ipaddress', ADD),
                change=_perms('room_schedules.room', CHANGE)
                + _perms('room_schedules.ipaddress', ADD, CHANGE, DELETE)
                + _perms('estate.roomlink', CHANGE, DELETE),
                delete=_perms('room_schedules.room', DELETE)
                + _perms('estate.roomlink', DELETE),
            )),
        Row('room_groups', 'Room groups',
            "Sets of display rooms shown together on one display.",
            actions=_model_rows(
                view=_perms('room_schedules.roomgroup', VIEW)
                + _perms('room_schedules.ipaddress', VIEW),
                add=_perms('room_schedules.roomgroup', ADD)
                + _perms('room_schedules.ipaddress', ADD),
                change=_perms('room_schedules.roomgroup', CHANGE)
                + _perms('room_schedules.ipaddress', ADD, CHANGE, DELETE),
                delete=_perms('room_schedules.roomgroup', DELETE),
            )),
    )),
    Section('Task Management', (
        Row('periodic_tasks', 'Periodic tasks',
            "The timetable for the system's own background jobs, such as the "
            "nightly estate sync. Not screen schedules. A wrong change here can "
            "stop those jobs running.",
            actions={
                action: sum((_perms(f'django_celery_beat.{model}', action)
                             for model in ('periodictask', 'intervalschedule',
                                           'crontabschedule', 'solarschedule',
                                           'clockedschedule')), ())
                for action in (VIEW, ADD, CHANGE, DELETE)
            }),
        Row('task_results', 'Task results',
            "The log of background jobs that have run.",
            actions={
                VIEW: _perms('django_celery_results.taskresult', VIEW)
                + _perms('django_celery_results.groupresult', VIEW),
                DELETE: _perms('django_celery_results.taskresult', DELETE)
                + _perms('django_celery_results.groupresult', DELETE),
            }),
    )),
    Section('Users, Groups & Teams', (
        Row('users', 'Users',
            "Accounts, and which groups they are in. Teams, location groups "
            "and superuser status stay with superusers.",
            actions=_model_rows(*((p,) for p in _all('auth.user'))),
            warning="Edit is administrator access: it can put anyone, "
                    "themselves included, into any group."),
        Row('groups', 'Groups',
            "These permission sets.",
            actions=_model_rows(*((p,) for p in _all('auth.group'))),
            warning="Edit is administrator access: it can grant any "
                    "permission on this page, to their own group included."),
        Row('account', 'Account',
            "",
            extras=(
                Extra('account:inactivity_exempt',
                      "Never removed for inactivity",
                      "For accounts meant to sit unused, such as the emergency "
                      "password account. Usually given through the Exempt "
                      "from inactivity removal group.",
                      ('screens.exempt_from_inactivity_removal',)),
            )),
    )),
    Section('Help', (
        Row('help', 'Documentation', "",
            extras=(
                Extra('help:technical_docs', "Technical documentation",
                      "Access, devices, room integration and operations. "
                      "Everyone can read Help & Tutorials.",
                      ('helpdocs.view_technical_docs',)),
            )),
    )),
)


_INTERNAL = "Django internals; nothing in this interface uses it."
_SUPERUSER_ONLY = ("Superuser-only, whatever permissions are held: granting "
                   "access is not something a permission can delegate.")
_NO_ADMIN = "Has no page in the admin."

#: Every permission not offered by the grid, with why. A permission is offered
#: or hidden, never both, and never neither — the tests enforce all three.
HIDDEN = {
    **dict.fromkeys(_all('admin.logentry'),
                    "The change history, written automatically."),
    **dict.fromkeys(_all('auth.permission'), _INTERNAL),
    **dict.fromkeys(_all('contenttypes.contenttype'), _INTERNAL),
    **dict.fromkeys(_all('sessions.session'), _INTERNAL),
    **dict.fromkeys(
        sum((_all(f'recurrence.{m}') for m in ('date', 'param', 'recurrence', 'rule')), ()),
        "Internal to the repeat rules on a schedule; covered by Schedules."),
    **dict.fromkeys(_all('django_celery_beat.periodictasks'),
                    "Bookkeeping the task scheduler keeps for itself."),
    **dict.fromkeys(_all('django_celery_results.chordcounter'),
                    "Bookkeeping the task worker keeps for itself."),
    **dict.fromkeys(
        _perms('django_celery_results.taskresult', ADD, CHANGE)
        + _perms('django_celery_results.groupresult', ADD, CHANGE),
        "Results are written by the worker, not by people."),
    **dict.fromkeys(_all('screens.userpreference'),
                    "Each person's accent colour, set from their own menu."),
    **dict.fromkeys(_all('screens.screenstatusevent'),
                    "Status history, written by the status check and shown "
                    "on the screen page."),
    **dict.fromkeys(_all('room_schedules.event'), _NO_ADMIN),
    **dict.fromkeys(_all('room_schedules.o365room'),
                    "The O365 rooms pages check Room Schedules → Rooms → Edit."),
    **dict.fromkeys(
        _perms('estate.campus', ADD, CHANGE, DELETE)
        + _perms('estate.building', ADD, CHANGE, DELETE)
        + _perms('estate.room', ADD, CHANGE, DELETE),
        "The estate is a read-only mirror; nobody can edit it."),
    **dict.fromkeys(
        _perms('estate.buildinglink', ADD) + _perms('estate.roomlink', ADD),
        "Links are made on the Link display rooms page, which checks Room "
        "Schedules → Rooms → Edit."),
    **dict.fromkeys(
        _all('screens.team') + _all('screens.teammembership')
        + _all('estate.locationgroup') + _all('estate.locationgroupmembership'),
        _SUPERUSER_ONLY),
}


# ---- Derived lookups ------------------------------------------------------

@dataclass(frozen=True)
class Cell:
    """One tickable box: an action on a row, or an extra."""

    key: str
    row: Row
    action: str | None
    label: str
    permissions: tuple
    description: str = ''

    @property
    def primary(self):
        """The permission whose presence shows the box as ticked."""
        return self.permissions[0]


def _build_cells():
    cells = {}
    for section in SECTIONS:
        for row in section.rows:
            action_labels = dict(ACTIONS)
            for action, bundle in row.actions.items():
                key = f'{row.key}:{action}'
                cells[key] = Cell(key, row, action,
                                  f'{row.label} → {action_labels[action]}', bundle)
            for extra in row.extras:
                cells[extra.key] = Cell(extra.key, row, None, extra.label,
                                        extra.permissions, extra.description)
    return cells


#: Every tickable box, by key, in display order.
CELLS = _build_cells()

#: Every permission the grid can grant.
OFFERED = frozenset(p for cell in CELLS.values() for p in cell.permissions)


def implied(keys):
    """``keys`` plus every box they need ticked with them.

    Add, Edit and Delete each need View of the same row — Django lets a change
    permission stand in for view, but the sidebar asks for view by name — and
    a row's ``requires`` adds boxes on other rows.
    """
    result = set(keys)
    pending = list(result)
    while pending:
        cell = CELLS.get(pending.pop())
        if cell is None or cell.action is None:
            continue
        needed = list(cell.row.requires.get(cell.action, ()))
        if cell.action != VIEW and VIEW in cell.row.actions:
            needed.append(f'{cell.row.key}:{VIEW}')
        for key in needed:
            if key not in result:
                result.add(key)
                pending.append(key)
    return result


def permissions_for(keys):
    """Every permission the boxes ``keys`` grant, implications included."""
    return {p for key in implied(keys) for p in CELLS[key].permissions}


def ticked(held):
    """The boxes to show ticked for someone holding the permissions ``held``."""
    return {key for key, cell in CELLS.items() if cell.primary in held}


def bundles_containing(permission):
    """The boxes whose bundle includes ``permission``, for explaining it."""
    return [cell for cell in CELLS.values() if permission in cell.permissions]
