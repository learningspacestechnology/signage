"""The Learning Spaces Datastore HTTP client.

Driven through httpx.MockTransport rather than by patching the client, so the
request the code would really send -- URL and headers -- is what the assertions
see.
"""

import httpx
from django.test import SimpleTestCase, override_settings

from estate import lsd_requests
from estate.lsd_requests import fetch_rooms

BASE = 'https://lsd.example.ed.ac.uk/api'
FIRST = f"{BASE}/v1/signage/rooms/?page_size=1000"


def _rooms(n, start=0):
    return [{'id': f"r{i}", 'name': f"Room {i}",
             'campus_lst': 'Central North', 'campus_name_short': 'CN',
             'building': 'Appleton Tower'}
            for i in range(start, start + n)]


def _page(results, count, next_url=None):
    return {'count': count, 'next': next_url, 'previous': None,
            'results': results}


def _next(page):
    return f"{BASE}/v1/signage/rooms/?page={page}&page_size=1000"


def paged(total, page_size=1000, count_for_page=None):
    """A handler serving `total` rooms across pages, as the datastore does.

    `count_for_page` lets a test make the declared count drift mid-walk.
    """
    def handler(request):
        page = int(request.url.params.get('page', 1))
        start = (page - 1) * page_size
        results = _rooms(min(page_size, total - start), start=start)
        more = start + page_size < total
        count = count_for_page(page) if count_for_page else total
        return httpx.Response(200, json=_page(
            results, count, _next(page + 1) if more else None))
    return handler


def mock_client(handler):
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={'key': 'test-key'},
    )


@override_settings(
    LSD_API_BASE_URL=BASE,
    LSD_API_KEY='test-key',
    LSD_SYNC_TIMEOUT=5,
)
class FetchRoomsTests(SimpleTestCase):
    def test_it_walks_every_page_and_returns_one_list(self):
        calls = []

        def handler(request):
            calls.append(str(request.url))
            return paged(2620)(request)

        rows = fetch_rooms(client=mock_client(handler))

        self.assertEqual(len(rows), 2620)
        self.assertEqual(len(calls), 3)
        self.assertEqual({r['id'] for r in rows}, {f"r{i}" for i in range(2620)})

    def test_it_starts_at_the_signage_feed_with_the_largest_page(self):
        seen = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(200, json=_page(_rooms(1), 1))

        fetch_rooms(client=mock_client(handler))

        self.assertEqual(seen, [FIRST])

    def test_it_follows_next_rather_than_counting_pages(self):
        """`next` is the terminator; a page past the end is a 404, not []."""
        seen = []

        def handler(request):
            seen.append(str(request.url))
            return paged(1500)(request)

        fetch_rooms(client=mock_client(handler))

        self.assertEqual(seen, [FIRST, _next(2)])

    def test_an_empty_estate_is_not_an_error(self):
        rows = fetch_rooms(client=mock_client(
            lambda r: httpx.Response(200, json=_page([], 0))))
        self.assertEqual(rows, [])

    def test_a_count_that_moves_mid_walk_is_refused(self):
        """The skipped-row case: every later page agrees on the smaller total.

        A room deleted from page 1's range after page 1 was read shifts the
        first row of page 2 back into page 1. Pages 2 and 3 then both declare
        2619, and only the first page's 2620 shows anything is wrong.
        """
        handler = paged(2620, count_for_page=lambda p: 2620 if p == 1 else 2619)

        with self.assertRaises(RuntimeError) as ctx:
            fetch_rooms(client=mock_client(handler))
        self.assertIn('changed during the walk', str(ctx.exception))

    def test_rows_short_of_the_declared_count_are_refused(self):
        def handler(request):
            return httpx.Response(200, json=_page(_rooms(999), 1000))

        with self.assertRaises(RuntimeError) as ctx:
            fetch_rooms(client=mock_client(handler))
        self.assertIn('declared 1000', str(ctx.exception))

    def test_a_room_seen_on_two_pages_is_refused(self):
        """An insert mid-walk shifts rows forward; the total can still match."""
        def handler(request):
            if 'page=2' in str(request.url):
                return httpx.Response(200, json=_page(_rooms(1, start=999), 1001))
            return httpx.Response(200, json=_page(_rooms(1000), 1001, _next(2)))

        with self.assertRaises(RuntimeError) as ctx:
            fetch_rooms(client=mock_client(handler))
        self.assertIn('more than one page', str(ctx.exception))

    def test_rows_with_no_id_are_left_for_the_parser_to_skip(self):
        rows = [{'id': ''}, {'name': 'no id'}] + _rooms(1)
        got = fetch_rooms(client=mock_client(
            lambda r: httpx.Response(200, json=_page(rows, 3))))
        self.assertEqual(len(got), 3)

    def test_a_next_link_to_another_host_is_refused_before_it_is_called(self):
        """The client carries the key; it must not follow it off-site."""
        hosts = []

        def handler(request):
            hosts.append(request.url.host)
            return httpx.Response(200, json=_page(
                _rooms(1000), 2000,
                'https://elsewhere.example.com/api/v1/signage/rooms/?page=2'))

        with self.assertRaises(RuntimeError) as ctx:
            fetch_rooms(client=mock_client(handler))

        self.assertEqual(hosts, ['lsd.example.ed.ac.uk'])
        self.assertIn('off the configured host', str(ctx.exception))

    def test_a_downgrade_to_http_is_refused_too(self):
        def handler(request):
            return httpx.Response(200, json=_page(
                _rooms(1000), 2000,
                'http://lsd.example.ed.ac.uk/api/v1/signage/rooms/?page=2'))

        with self.assertRaises(RuntimeError):
            fetch_rooms(client=mock_client(handler))

    def test_a_next_link_that_never_ends_is_cut_off(self):
        calls = []

        def handler(request):
            calls.append(request)
            # Always another page, never any new rows.
            return httpx.Response(200, json=_page([], 10, _next(len(calls) + 1)))

        with self.assertRaises(RuntimeError) as ctx:
            fetch_rooms(client=mock_client(handler))
        self.assertIn('not terminating', str(ctx.exception))
        self.assertLessEqual(len(calls), 3)

    def test_a_non_200_raises_with_the_status_and_url(self):
        def handler(request):
            return httpx.Response(503, text="upstream unavailable")

        with self.assertRaises(RuntimeError) as ctx:
            fetch_rooms(client=mock_client(handler))

        message = str(ctx.exception)
        self.assertIn("503", message)
        self.assertIn("/v1/signage/rooms/", message)
        self.assertIn("upstream unavailable", message)

    def test_a_failure_on_a_later_page_raises_rather_than_returning_half(self):
        def handler(request):
            if 'page=2' in str(request.url):
                return httpx.Response(404, json={'detail': 'Invalid page.'})
            return httpx.Response(200, json=_page(_rooms(1000), 2000, _next(2)))

        with self.assertRaises(RuntimeError) as ctx:
            fetch_rooms(client=mock_client(handler))
        self.assertIn("404", str(ctx.exception))

    def test_the_error_never_carries_the_api_key(self):
        """The message reaches worker logs and admin-visible task results."""
        def handler(request):
            return httpx.Response(401, text="unauthorised")

        with self.assertRaises(RuntimeError) as ctx:
            fetch_rooms(client=mock_client(handler))

        self.assertNotIn('test-key', str(ctx.exception))

    def test_a_bare_list_is_refused_rather_than_misread(self):
        """That is /v1/rooms/'s shape: the URL is pointing at the wrong feed."""
        def handler(request):
            return httpx.Response(200, json=_rooms(200))

        with self.assertRaises(RuntimeError) as ctx:
            fetch_rooms(client=mock_client(handler))
        self.assertIn('expected a paginated envelope', str(ctx.exception))

    def test_an_envelope_with_no_count_is_refused(self):
        def handler(request):
            return httpx.Response(200, json={'results': _rooms(2), 'next': None})

        with self.assertRaises(RuntimeError):
            fetch_rooms(client=mock_client(handler))


@override_settings(LSD_API_BASE_URL=BASE, LSD_API_KEY='test-key',
                   LSD_SYNC_TIMEOUT=5)
class BuiltClientTests(SimpleTestCase):
    def test_the_real_client_asks_for_gzip(self):
        """~20x fewer bytes for this feed; httpx does it, this pins it."""
        client = lsd_requests._build_client()
        try:
            self.assertIn('gzip', client.headers['accept-encoding'])
            self.assertEqual(client.headers['key'], 'test-key')
        finally:
            client.close()


class HeaderTests(SimpleTestCase):
    @override_settings(LSD_API_KEY='shhh')
    def test_the_key_travels_as_a_header(self):
        self.assertEqual(lsd_requests._headers()['key'], 'shhh')

    @override_settings(LSD_API_KEY='')
    def test_a_blank_key_refuses_the_run_rather_than_calling_out(self):
        with self.assertRaises(RuntimeError) as ctx:
            lsd_requests._headers()
        self.assertIn('LSD_API_KEY', str(ctx.exception))

    @override_settings(LSD_API_KEY='shhh',
                       LSD_API_BASE_URL='https://lsd.example.ed.ac.uk/api/')
    def test_a_trailing_slash_on_the_base_url_does_not_double_up(self):
        self.assertEqual(lsd_requests._base_url(), 'https://lsd.example.ed.ac.uk/api')
