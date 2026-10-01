"""HTTP client for the Learning Spaces Datastore.

Conventions follow `room_schedules/o365_requests.py`, the project's other
external integration: httpx rather than requests (which is not a dependency),
explicit timeouts, and a RuntimeError carrying status, URL and body on any
non-2xx — which is the exception the Celery task lists in `autoretry_for`.
"""

import math

import httpx
from django.conf import settings

#: The dedicated signage feed. Not /v1/rooms/ (a bare array with no count, and
#: a different field set) nor /v1/export/rooms/ (centrally managed teaching
#: space only) — see CLAUDE.md's "Estate directory" before switching.
ROOMS_PATH = '/v1/signage/rooms/'

#: The datastore's own cap. A larger value is silently clamped to this, so
#: asking for more would not mean fewer pages — only a misleading URL.
PAGE_SIZE = 1000


def _base_url():
    return settings.LSD_API_BASE_URL.rstrip('/')


def _headers():
    """Auth headers, or a RuntimeError naming the missing setting.

    Read through django.conf.settings on every call rather than bound at
    import, so override_settings works and a blank key is a per-run failure
    rather than a startup one.
    """
    key = getattr(settings, 'LSD_API_KEY', '')
    if not key:
        raise RuntimeError(
            "LSD_API_KEY is not set; the estate sync cannot run. Set it in "
            "advertising/settings.py for development, or in .env in production."
        )
    return {"key": key, "Accept": "application/json"}


def _build_client():
    """The seam tests replace with an httpx.MockTransport-backed client.

    No Accept-Encoding header is set here because httpx already sends
    ``gzip, deflate`` and decompresses transparently — roughly a twentieth of
    the bytes for this feed, for no code.
    """
    return httpx.Client(
        timeout=httpx.Timeout(10.0, read=float(settings.LSD_SYNC_TIMEOUT)),
        headers=_headers(),
    )


def _same_origin(url, base):
    return (url.scheme, url.host, url.port) == (base.scheme, base.host, base.port)


def _get_page(client, url):
    """One page of the envelope, or a RuntimeError saying what was wrong."""
    resp = client.get(url)
    if resp.status_code != 200:
        # Status, URL and body — never headers. This string reaches worker
        # logs *and* admin-visible django_celery_results rows, and the API
        # key travels in a header.
        raise RuntimeError(
            f"LSD API error {resp.status_code} for {url}: {resp.text}")
    payload = resp.json()
    if (not isinstance(payload, dict)
            or not isinstance(payload.get('results'), list)
            or not isinstance(payload.get('count'), int)):
        # A bare list is refused too: that is /v1/rooms/'s shape, and reading
        # it here would mean the base URL or path is pointing somewhere else.
        raise RuntimeError(
            f"LSD API returned {type(payload).__name__}, expected a paginated "
            f"envelope with 'count' and 'results', for {url}")
    return payload


def fetch_rooms(client=None):
    """Every room from GET {base}/v1/signage/rooms/, as one list of dicts.

    The feed is paginated, so this walks ``next`` until it is null and returns
    the pages concatenated. The whole walk completes before the caller writes
    anything, and every inconsistency below is a RuntimeError — which the
    task retries — rather than a partial list, because the reconciler deletes
    rooms by their absence:

    - ``count`` is pinned from the **first** page. The server recomputes it
      per request, so a value that moves mid-walk means rows were inserted or
      deleted under us. That is when a row can slide across a page boundary
      into a page already read, and be skipped with every later page
      agreeing on the smaller total. Comparing against the first page is what
      catches it; comparing against the last would not.
    - The rows collected must match that count, with no id seen twice.
    - ``next`` must stay on the configured host. The client carries the API
      key, so following a URL the response names would send the key to
      whichever host that is.
    """
    base = httpx.URL(_base_url())
    url = f"{_base_url()}{ROOMS_PATH}?page_size={PAGE_SIZE}"
    owns_client = client is None
    client = client or _build_client()

    rows = []
    try:
        page = _get_page(client, url)
        expected = page['count']
        # One spare page of slack, so a loop in `next` fails rather than
        # walking forever, without refusing a legitimate final short page.
        max_pages = math.ceil(expected / PAGE_SIZE) + 1
        pages = 1
        while True:
            if page['count'] != expected:
                raise RuntimeError(
                    f"LSD room count changed during the walk, from {expected} "
                    f"to {page['count']} at {url}. The feed moved under the "
                    f"read; nothing was written, and the run will retry.")
            rows.extend(page['results'])

            next_url = page.get('next')
            if not next_url:
                break
            if not _same_origin(httpx.URL(next_url), base):
                raise RuntimeError(
                    f"LSD API 'next' points off the configured host "
                    f"({next_url}); refusing to send the API key there.")
            pages += 1
            if pages > max_pages:
                raise RuntimeError(
                    f"LSD API walk exceeded {max_pages} pages for {expected} "
                    f"rooms; 'next' is not terminating.")
            url = next_url
            page = _get_page(client, url)
    finally:
        if owns_client:
            client.close()

    if len(rows) != expected:
        raise RuntimeError(
            f"LSD API returned {len(rows)} rooms but declared {expected}; "
            f"refusing to reconcile against an incomplete estate.")
    # Id-less rows are the parser's to skip, not a sign of a shifted boundary.
    ids = [row['id'] for row in rows if isinstance(row, dict) and row.get('id')]
    if len(ids) != len(set(ids)):
        raise RuntimeError(
            "LSD API returned the same room id on more than one page; the "
            "page boundaries shifted during the walk.")
    return rows
