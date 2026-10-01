"""Room context on the meta endpoint.

The payload is additive and inert: nothing in the current player reads
`meta.room`. What matters here is that adding it cannot disturb what the player
*does* read — `playlist_last_updated`, which /api/screen and /api/meta must
still agree on byte for byte (see the header of test_playlist_json.py).
"""

import json

from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from estate.models import Building, Campus, Room
from screens.models import Playlist, Schedule, Screen, Team
from screens.views import _UNCONFIGURED_META


# The gate is not what is under test here, and /api/meta/<id> is deliberately
# behind it -- same treatment as test_playlist_json.py's endpoint tests.
@override_settings(IP_ACCESS_CONTROL_ENABLED=False)
class MetaRoomContextTests(TestCase):
    def setUp(self):
        Team.objects.all().delete()
        self.team = Team.objects.create(name="Alpha")
        self.playlist = Playlist.objects.create(name="p")
        self.playlist.teams.add(self.team)
        self.schedule = Schedule.objects.create(
            name="s", default_playlist=self.playlist)
        self.schedule.teams.add(self.team)

        campus = Campus.objects.create(name="Central", code="CN")
        self.building = Building.objects.create(
            key="AT", name="Appleton Tower", campus=campus)
        self.room = Room.objects.create(
            lsd_id="EASTER-1234", name="LT2", building=self.building,
            room_status="General Teaching",
            capacity=200, latitude="55.944500", longitude="-3.187200",
            service_provider="LST", voip_number=505000)

        self.screen = self._screen("placed", "10.0.0.1", self.room)
        self.unplaced = self._screen("unplaced", "10.0.0.2", None)
        self.client = Client()

    def _screen(self, name, ip, room, schedule=...):
        screen = Screen.objects.create(
            name=name, ip=ip, room=room,
            schedule=self.schedule if schedule is ... else schedule)
        screen.teams.add(self.team)
        return screen

    def _meta(self, screen):
        resp = self.client.get(f'/api/meta/{screen.pk}')
        self.assertEqual(resp.status_code, 200)
        return json.loads(resp.content)

    # --- the payload --------------------------------------------------------

    def test_a_placed_screen_reports_its_room(self):
        room = self._meta(self.screen)['room']
        self.assertEqual(room['id'], "EASTER-1234")
        self.assertEqual(room['name'], "LT2")
        self.assertEqual(room['building'], {"name": "Appleton Tower"})
        self.assertEqual(room['campus'], {"name": "Central", "code": "CN"})
        self.assertEqual(room['capacity'], 200)
        self.assertEqual(room['room_status'], "General Teaching")
        self.assertIs(room['active'], True)
        self.assertEqual(room['latitude'], "55.944500")
        self.assertEqual(room['support'], {"provider": "LST", "voip": 505000})

    def test_an_inactive_room_says_so(self):
        Room.objects.filter(pk=self.room.pk).update(active=False)
        self.assertIs(self._meta(self.screen)['room']['active'], False)

    def test_the_fields_the_feed_no_longer_carries_are_not_sent(self):
        """The signage feed dropped them; a key that is always null is noise."""
        room = self._meta(self.screen)['room']
        self.assertNotIn('usage', room)
        self.assertNotIn('group', room['support'])

    def test_an_unplaced_screen_reports_null_not_a_missing_key(self):
        payload = self._meta(self.unplaced)
        self.assertIn('room', payload)
        self.assertIsNone(payload['room'])

    def test_every_optional_value_serialises_as_null_rather_than_empty_string(self):
        bare = Room.objects.create(
            lsd_id="r2", name="Cupboard", building=self.building)
        Screen.objects.filter(pk=self.screen.pk).update(room=bare)

        room = self._meta(self.screen)['room']
        for key in ('latitude', 'longitude', 'room_status', 'capacity'):
            self.assertIsNone(room[key], key)
        self.assertEqual(room['support'], {"provider": None, "voip": None})

    def test_a_campus_with_no_short_code_reports_null(self):
        Campus.objects.filter(pk=self.building.campus_id).update(code='')
        self.assertIsNone(self._meta(self.screen)['room']['campus']['code'])

    # --- the three exits ----------------------------------------------------

    def test_a_screen_with_no_schedule_still_reports_its_room(self):
        """A device with no schedule is polling perfectly happily."""
        Screen.objects.filter(pk=self.screen.pk).update(schedule=None)
        payload = self._meta(self.screen)
        self.assertEqual(payload['current_playlist'], -1)
        self.assertEqual(payload['room']['name'], "LT2")

    def test_the_unconfigured_constant_is_not_mutated_by_that_branch(self):
        """It is module-level and shared with every unrecognised device.

        Writing into it would leak one screen's room to the whole network.
        """
        Screen.objects.filter(pk=self.screen.pk).update(schedule=None)
        self._meta(self.screen)
        self.assertIsNone(_UNCONFIGURED_META['room'])

    def test_an_unrecognised_device_gets_the_same_shape_with_no_room(self):
        payload = json.loads(self.client.get('/api/meta').content)
        self.assertIn('room', payload)
        self.assertIsNone(payload['room'])

    def test_the_ticker_branch_carries_the_room_and_keeps_its_sentinels(self):
        Screen.objects.filter(pk=self.screen.pk).update(
            ticker_enabled=True, ticker_text="Fire drill at 3pm")
        payload = self._meta(self.screen)

        self.assertEqual(payload['room']['name'], "LT2")
        self.assertTrue(payload['ticker_enabled'])
        self.assertEqual(payload['current_playlist'], -1)
        self.assertEqual(payload['playlist_last_updated'], "1970-01-01T00:00:00")

    # --- what must not have changed -----------------------------------------

    def test_the_playlist_endpoint_and_meta_still_agree_byte_for_byte(self):
        """The player diffs this string; the two endpoints must not drift."""
        meta = self._meta(self.screen)
        screen_json = json.loads(
            self.client.get(f'/api/screen/{self.screen.pk}').content)
        self.assertEqual(
            meta['playlist_last_updated'], screen_json['playlist_last_updated'])

    def test_the_playlist_payload_gains_no_room_key(self):
        """One endpoint carries it; /api/screen is left exactly as it was."""
        payload = json.loads(
            self.client.get(f'/api/screen/{self.screen.pk}').content)
        self.assertNotIn('room', payload)

    def test_assigning_a_room_republishes_without_meta_having_to_say_so(self):
        """Screen.last_updated is auto_now and folds into the published
        timestamp, so the player refetches on its own."""
        before = self._meta(self.screen)['playlist_last_updated']
        other = Room.objects.create(lsd_id="r9", name="LT9", building=self.building)
        self.screen.room = other
        self.screen.save()
        self.assertNotEqual(self._meta(self.screen)['playlist_last_updated'], before)

    # --- cost ---------------------------------------------------------------

    def test_the_heartbeat_does_not_walk_the_room_chain_lazily(self):
        """This runs once a minute for every device in the estate."""
        self._meta(self.screen)  # warm content types etc.
        with CaptureQueriesContext(connection) as placed:
            self._meta(self.screen)
        with CaptureQueriesContext(connection) as unplaced:
            self._meta(self.unplaced)

        # Reporting a room must not cost more queries than not reporting one.
        self.assertLessEqual(len(placed), len(unplaced))

    @override_settings(AUTO_MAKE_SCREENS_FOR_NEW_IPS=False)
    def test_the_ip_lookup_path_is_prefetched_too(self):
        client = Client(REMOTE_ADDR="10.0.0.1")
        with CaptureQueriesContext(connection) as ip_path:
            payload = json.loads(client.get('/api/meta').content)
        self.assertEqual(payload['room']['name'], "LT2")

        joined = " ".join(q['sql'] for q in ip_path.captured_queries)
        self.assertIn("estate_building", joined)
        self.assertIn("estate_campus", joined)
