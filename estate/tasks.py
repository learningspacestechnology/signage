import logging

import httpx
from celery import shared_task
from django.db import transaction

# Imported at module scope so tests can patch `estate.tasks.fetch_rooms`
# — the import site, not the source module. Same convention as
# room_schedules/tests/test_o365_sync.py.
from estate.lsd_requests import fetch_rooms
from estate.sync import reconcile_estate

logger = logging.getLogger(__name__)


@shared_task(
    name='estate.tasks.sync_estate',
    autoretry_for=(RuntimeError, httpx.TimeoutException, httpx.TransportError, OSError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
    # Longer than sync_o365_rooms' 300/330: a few thousand rooms through
    # update_or_create is roughly twice that many queries.
    soft_time_limit=600,
    time_limit=660,
)
def sync_estate():
    """Mirror the Learning Spaces Datastore room feed into the estate app.

    The whole feed is fetched before anything is written, so an HTTP failure
    retries against an untouched database rather than reconciling against half
    an estate. The write phase is one transaction for the same reason — a soft
    time limit rolls it back.

    Returns a summary dict, which lands in django_celery_results and so is
    readable from the admin without going near a worker log.
    """
    rows = fetch_rooms()
    with transaction.atomic():
        summary = reconcile_estate(rows)
    logger.info("sync_estate: %s", summary)
    return summary
