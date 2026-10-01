"""Reconcile the Learning Spaces Datastore room feed into the local mirror.

Pure functions over a list of dicts: no HTTP, no Celery. `estate.tasks` fetches
and wraps this in a transaction; everything below can be tested by handing it a
payload.

The shape of the problem, which drives most of the design: the feed is **flat**.
Campus and building arrive as strings on every room row, and there is no
buildings or campuses endpoint to reconcile against. Both are therefore
*derived* from the distinct values across the whole response, and neither
carries a code that could serve as a key. `campus_name_short` is dirty enough
(case variants, blanks) that it is kept as an attribute rather than an
identifier. `building_code` is Estates' own code and is many-to-many with the
building names, so it is kept per room rather than keying buildings.
"""

import hashlib
import logging
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from estate.models import Building, Campus, Room

logger = logging.getLogger(__name__)


# --- normalisation ---------------------------------------------------------

def norm(text):
    """Casefold and collapse whitespace. The identity used for derived keys."""
    return ' '.join((text or '').split()).casefold()


def building_key(campus_name, building_name):
    """The natural key for a building: its campus and its name.

    The campus is part of the key because it has to be — "Medical School"
    exists on two different campuses in the live data, and they are two
    different buildings.

    The feed's `building_code` cannot stand in for this: one code covers two
    of our building names in places and one name carries several codes in
    others. So a building renamed upstream becomes a *new* building here and
    the old one is reconciled away once nothing is left in it. Rooms are keyed
    on their own id and so survive that intact; only the Building row churns.
    """
    key = f"{norm(campus_name)}|{norm(building_name)}"
    if len(key) > 255:
        # Truncating alone could collide two long names into one building, so
        # keep a digest of the whole thing.
        digest = hashlib.blake2s(key.encode('utf-8'), digest_size=4).hexdigest()
        key = f"{key[:246]}:{digest}"
    return key


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal_or_none(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _text(value, limit):
    """A trimmed string, capped, with a literal "None" treated as blank.

    The older /v1/rooms/ feed sent several columns as the four-character
    string "None" rather than a JSON null. The signage feed normalises the
    three that did to null, and none has been seen since, but the fold costs
    nothing and keeps the word "None" from ever reaching an operator as if it
    were a real service provider.
    """
    text = str(value).strip() if value is not None else ''
    if text == 'None':
        text = ''
    return text[:limit]


def _active(value):
    """Only an explicit JSON false makes a room inactive.

    Anything else — a missing key, a null, a stray string — reads as active.
    Inactive rooms flag the screens in them, so malformed data should fail
    towards no flag rather than towards a list of false alarms.
    """
    return value is not False


def parse_row(row):
    """One feed row as the fields we mirror, or None if it is unusable."""
    lsd_id = (row.get('id') or '').strip()
    if not lsd_id:
        return None

    return {
        'lsd_id': lsd_id[:255],
        # An unnamed room still has to be selectable in the room picker, so
        # fall back to its id rather than showing a blank row.
        'name': (_text(row.get('name'), 255) or lsd_id),
        # campus_lst is the identity; campus_name_short is an attribute, and
        # the feed's `campus` is a different, public grouping altogether.
        'campus_name': _text(row.get('campus_lst'), 200),
        'campus_code': _text(row.get('campus_name_short'), 20),
        'building_name': _text(row.get('building'), 255),
        'public_campus': _text(row.get('campus'), 200),

        'room_status': _text(row.get('room_status'), 100),
        'capacity': _int_or_none(row.get('capacity')),
        'active': _active(row.get('active')),

        'latitude': _decimal_or_none(row.get('latitude')),
        'longitude': _decimal_or_none(row.get('longitude')),
        # Upstream mixes CRLF and LF, so one building's rooms otherwise show
        # two "different" addresses that differ only in line endings.
        'address': _text(row.get('address'), 500).replace('\r\n', '\n'),
        'building_code': _text(row.get('building_code'), 20),

        'support_type': _text(row.get('support_type'), 100),
        'service_provider': _text(row.get('service_provider'), 200),
        'voip_number': _int_or_none(row.get('voip_number')),
        'optime_index': _int_or_none(row.get('optime_index')),
    }


# --- reconciliation --------------------------------------------------------

def _modal(values):
    """The most common value, ties broken by sort order so runs are stable."""
    counts = Counter(values)
    top = counts.most_common()
    best = top[0][1]
    return sorted(v for v, n in top if n == best)[0]


def _referenced_pks(model, candidate_pks):
    """Which of ``candidate_pks`` any other row still points at.

    Walks ``_meta.related_objects`` rather than naming ``Screen.room`` and
    ``RoomLink.estate_room`` explicitly. A hand-written list of dependants is
    exactly the thing that goes stale, and going stale here turns "flag it"
    silently back into "delete it" — unlinking a screen from its room.
    """
    referenced = set()
    if not candidate_pks:
        return referenced
    for rel in model._meta.related_objects:
        field = getattr(rel, 'field', None)
        if field is None:
            continue
        path = f"{field.name}__pk__in"
        referenced.update(
            rel.related_model._base_manager
            .filter(**{path: candidate_pks})
            .values_list(f"{field.name}__pk", flat=True)
        )
    return referenced


def _sweep(model, run_started, summary_prefix, summary):
    """Delete stale rows nothing depends on; flag the ones something does."""
    stale = model._base_manager.filter(
        Q(last_seen_at__lt=run_started) | Q(last_seen_at__isnull=True))
    stale_pks = list(stale.values_list('pk', flat=True))
    if not stale_pks:
        return
    referenced = _referenced_pks(model, stale_pks)
    doomed = [pk for pk in stale_pks if pk not in referenced]
    if doomed:
        summary[f'{summary_prefix}_deleted'] = (
            model._base_manager.filter(pk__in=doomed).delete()[0])
    if referenced:
        summary[f'{summary_prefix}_flagged'] = (
            model._base_manager
            .filter(pk__in=referenced, missing_from_source=False)
            .update(missing_from_source=True))


def _should_reconcile(rows, summary):
    """False when the payload looks too small to trust with deletions.

    The worst failure this task has is the datastore shipping a truncated or
    filtered response and the sync then flagging or deleting the whole estate,
    unlinking every screen. The client's check against the feed's declared
    `count` catches a short *read*; this is the second line, for a response
    that is complete by its own count but wrong — a filter applied upstream by
    mistake, say. Refusing to delete is always recoverable; deleting is not.
    """
    min_rooms = int(getattr(settings, 'LSD_SYNC_MIN_ROOMS', 1))
    max_shrink = int(getattr(settings, 'LSD_SYNC_MAX_SHRINK_PCT', 50))

    if len(rows) < min_rooms:
        summary['reason'] = 'below_min_rooms'
        logger.error(
            "estate sync: feed returned %d rooms, below LSD_SYNC_MIN_ROOMS "
            "(%d). Updates applied; nothing deleted or flagged.",
            len(rows), min_rooms)
        return False

    held = Room._base_manager.filter(missing_from_source=False).count()
    if held and len(rows) < held * (100 - max_shrink) / 100:
        summary['reason'] = 'shrink_guard'
        logger.error(
            "estate sync: feed returned %d rooms against %d held, a shrink of "
            "more than LSD_SYNC_MAX_SHRINK_PCT (%d%%). Updates applied; "
            "nothing deleted or flagged.", len(rows), held, max_shrink)
        return False

    return True


def reconcile_estate(rows, run_started=None):
    """Mirror ``rows`` into Campus/Building/Room and return a run summary."""
    run_started = run_started or timezone.now()
    summary = {
        'rooms': 0, 'rooms_created': 0, 'skipped': 0,
        'buildings': 0, 'campuses': 0,
        'campus_code_conflicts': 0, 'room_campus_drift': 0,
        'reconciled': True,
    }

    parsed = []
    for row in rows:
        item = parse_row(row)
        if item is None or not (item['campus_name'] or item['building_name']):
            summary['skipped'] += 1
            continue
        parsed.append(item)

    campuses = _sync_campuses(parsed, run_started, summary)
    buildings = _sync_buildings(parsed, campuses, run_started, summary)
    _sync_rooms(parsed, buildings, run_started, summary)

    if _should_reconcile(rows, summary):
        # Children before parents, so a building emptied this run is deletable
        # in the same run rather than lingering until the next one.
        _sweep(Room, run_started, 'rooms', summary)
        _sweep(Building, run_started, 'buildings', summary)
        _sweep(Campus, run_started, 'campuses', summary)
    else:
        summary['reconciled'] = False

    return summary


def _sync_campuses(parsed, run_started, summary):
    """Upsert every campus named in the feed. Returns {norm(name): Campus}."""
    # campus_lst is the key, so near-duplicates differing only by case or
    # spacing are merged deliberately: it is free text upstream, and a merge is
    # far less damaging than two half-populated campuses.
    names = defaultdict(list)
    codes = defaultdict(list)
    for item in parsed:
        key = norm(item['campus_name'] or 'Unknown')
        names[key].append(item['campus_name'] or 'Unknown')
        if item['campus_code']:
            codes[key].append(item['campus_code'].upper())

    resolved = {}
    for key, display_names in names.items():
        seen = codes.get(key, [])
        if len(set(seen)) > 1:
            summary['campus_code_conflicts'] += 1
        campus, _ = Campus.objects.update_or_create(
            name=_modal(display_names),
            defaults={
                # Majority wins, and blanks do not vote: the short code arrives
                # missing on a handful of rows and in mixed case on others.
                'code': _modal(seen) if seen else '',
                'missing_from_source': False,
                'last_seen_at': run_started,
            },
        )
        resolved[key] = campus
    summary['campuses'] = len(resolved)
    return resolved


def _sync_buildings(parsed, campuses, run_started, summary):
    """Upsert every building derivable from the feed. Returns {key: Building}."""
    groups = defaultdict(list)
    for item in parsed:
        key = building_key(item['campus_name'], item['building_name'])
        item['_building_key'] = key
        groups[key].append(item)

    resolved = {}
    for key, items in groups.items():
        names = [i['building_name'] for i in items if i['building_name']]
        name = (_modal(names) if names else 'Unknown')[:255]
        campus = campuses[norm(items[0]['campus_name'] or 'Unknown')]

        building, _ = Building.objects.update_or_create(
            key=key,
            defaults={
                'name': name,
                'campus': campus,
                'missing_from_source': False,
                'last_seen_at': run_started,
            },
        )
        resolved[key] = building

    summary['buildings'] = len({b.pk for b in resolved.values()})
    return resolved


def _sync_rooms(parsed, buildings, run_started, summary):
    created = 0
    for item in parsed:
        building = buildings[item['_building_key']]
        if norm(item['campus_name'] or 'Unknown') != norm(building.campus.name):
            summary['room_campus_drift'] += 1

        _, was_created = Room.objects.update_or_create(
            lsd_id=item['lsd_id'],
            defaults={
                'name': item['name'],
                'building': building,
                'room_status': item['room_status'],
                'capacity': item['capacity'],
                'active': item['active'],
                'latitude': item['latitude'],
                'longitude': item['longitude'],
                'address': item['address'],
                'building_code': item['building_code'],
                'public_campus': item['public_campus'],
                'support_type': item['support_type'],
                'service_provider': item['service_provider'],
                'voip_number': item['voip_number'],
                'optime_index': item['optime_index'],
                'missing_from_source': False,
                'last_seen_at': run_started,
            },
        )
        created += was_created
    summary['rooms'] = len(parsed)
    summary['rooms_created'] = created
