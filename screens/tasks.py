import datetime
import ipaddress
import logging
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.db.models import F, Max
from screens.models import ScreenStatusEvent, Source, ScheduleRule, Screen

logger = logging.getLogger(__name__)

@shared_task(name='screens.tasks.cleanup_sources')
def cleanup_sources():
    Source.objects.filter(expires_at__lte=datetime.datetime.now()).delete()

@shared_task(name='screens.tasks.update_playlists')
def update_playlists():
    # Find sources with playlists whose last_updated (meta time) is less than the source's valid_from
    sources_to_update = Source.objects.filter(
        valid_from__isnull=False,
        playlists__last_updated__lt=F('valid_from'),
        valid_from__lte=timezone.now()
    ).distinct()

    for source in sources_to_update:
        print(f"Updating playlists for source {source}")
        source.meta_times_touch()

@shared_task(name='screens.tasks.cleanup_schedule')
def cleanup_schedule():
    for rule in filter(lambda x: x.is_expired(), ScheduleRule.objects.all()):
        rule.delete()


def _ping(ip, timeout):
    """Whether the host answers a single ICMP echo.

    True/False are answers; None means the probe could not be run at all, which
    is not the same thing and must not be recorded as a failure. The case that
    matters is `ping` missing from the image -- see _probe_screens.
    """
    try:
        family = "-6" if ipaddress.ip_address(ip).version == 6 else "-4"
    except ValueError:
        # GenericIPAddressField validates on save, so this should be
        # unreachable; a malformed row must not take the whole cycle down.
        logger.warning("Skipping screen probe: %r is not a valid IP address", ip)
        return None
    try:
        completed = subprocess.run(
            ["ping", family, "-c", "1", "-W", str(timeout), "-n", ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # ping's own -W should end it first; this is the backstop for a
            # process that hangs before it ever starts counting.
            timeout=timeout + 2,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return False
    return completed.returncode == 0


def _probe_screens():
    """Ping the screens that are not currently reporting, and record the result.

    Only non-online screens are probed. A screen that is already polling has
    answered the more useful question by definition, so probing it adds network
    noise and tells us nothing.

    Returns the number of screens probed, for logging and tests.
    """
    if not getattr(settings, "SCREEN_PROBE_ENABLED", False):
        return 0

    if shutil.which("ping") is None:
        # Checked once up front rather than discovered per screen. Deliberately
        # not recorded as a failed probe: nothing was asked of the network, and
        # writing last_ping_attempt here would turn "we cannot probe" into
        # "the screen did not answer", which is a different and wrong claim.
        logger.warning(
            "SCREEN_PROBE_ENABLED is on but `ping` is not installed, so screen "
            "reachability cannot be checked. Install iputils-ping in the image."
        )
        return 0

    timeout = int(getattr(settings, "SCREEN_PROBE_TIMEOUT", 1))
    targets = list(
        Screen.objects
        .exclude(last_seen__gte=Screen.online_cutoff())
        .values_list("pk", "ip")
    )
    if not targets:
        return 0

    concurrency = int(getattr(settings, "SCREEN_PROBE_CONCURRENCY", 16))
    workers = max(1, min(concurrency, len(targets)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda t: (t[0], _ping(t[1], timeout)), targets))

    now = timezone.now()
    reachable = [pk for pk, ok in results if ok is True]
    unreachable = [pk for pk, ok in results if ok is False]

    # Queryset .update(), never save(): .update() does not call pre_save() at
    # all, so Screen.last_updated's auto_now cannot fire. That field is the
    # publish signal -- moving it here would restart every attached device's
    # rotation from item one, once per probe cycle. See the note on
    # last_updated in screens/models/screen.py.
    if reachable:
        Screen.objects.filter(pk__in=reachable).update(
            last_ping_ok=now, last_ping_attempt=now)
    if unreachable:
        Screen.objects.filter(pk__in=unreachable).update(last_ping_attempt=now)

    return len(reachable) + len(unreachable)


def _record_status_transitions():
    """Append a ScreenStatusEvent for every screen whose status has changed.

    Runs over every screen, not just the probed ones: a screen coming back
    online is as much a transition as one going dark.

    The comparison uses the annotated derived_* values rather than calling
    status_and_reason() per row, so the whole estate is judged against one
    consistent clock instead of a `now` that drifts down the loop.

    Idempotent: a second run with nothing changed writes nothing.
    """
    now = timezone.now()
    events = [
        ScreenStatusEvent(
            screen_id=screen.pk,
            status=screen.derived_status,
            reason=screen.derived_reason,
            at=now,
        )
        for screen in Screen.objects.with_status()
        if (screen.recorded_status, screen.recorded_reason or "")
        != (screen.derived_status, screen.derived_reason)
    ]
    if events:
        ScreenStatusEvent.objects.bulk_create(events)
    return len(events)


@shared_task(
    name='screens.tasks.check_screens',
    soft_time_limit=300,
    time_limit=330,
)
def check_screens():
    """Probe unreachable screens, then record any status transitions.

    One task rather than two so the recorded status reflects the probe that
    just ran, instead of lagging it by a whole cycle. The recorder runs even
    when probing is disabled -- history is still worth keeping when the only
    signal is the heartbeat.
    """
    probed = _probe_screens()
    changed = _record_status_transitions()
    logger.info("check_screens: probed %d screen(s), recorded %d change(s)",
                probed, changed)


@shared_task(name='screens.tasks.cleanup_status_events')
def cleanup_status_events():
    """Prune status history, keeping each screen's most recent transition.

    That last row is exempt however old it is: it is the row that explains the
    state the screen is in now, so a screen dark for six months must not lose
    the record of when it went dark.

    Max("pk") identifies it rather than Max("at") because events are only ever
    appended forward in time, so id order and `at` order agree -- and unlike a
    DISTINCT ON this works on MariaDB and SQLite alike.
    """
    days = int(getattr(settings, "SCREEN_STATUS_HISTORY_DAYS", 90))
    cutoff = timezone.now() - datetime.timedelta(days=days)
    latest = list(
        ScreenStatusEvent.objects
        .values("screen_id")
        .annotate(latest=Max("pk"))
        .values_list("latest", flat=True)
    )
    ScreenStatusEvent.objects.filter(at__lt=cutoff).exclude(pk__in=latest).delete()
