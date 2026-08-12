"""The JSON contract the Vue player consumes.

This is the payload that broke when the player moved to playlist-based
interspersed content and the backend did not: the shape is load-bearing and was
previously untested end to end.

Two rules are worth stating because breaking either is silent:

* ``interspersed.playlist`` / ``interspersed.screen`` must be ``null`` or an
  object carrying an ``items`` array. The player reads ``.items.length`` with no
  optional chaining, so ``{}`` throws during render and the screen goes black.
* ``/api/screen/<id>`` and ``/api/meta/<id>`` must report byte-identical
  ``playlist_last_updated``. The player diffs them with a strict ``!==``, so any
  disagreement makes it refetch on every poll, for ever.
"""
import datetime

import time_machine
from django.test import Client, TestCase, override_settings

from screens.models import Playlist, PlaylistEntry, Schedule, Screen, Source
from screens.models.playlist import SINGLE_ITEM_HOLD_SECONDS
from screens.views import render_last_updated, render_playlist_json


def web_source(url):
    """Iframe sources keep these tests off the filesystem — Source.src() reads
    file.url for image and video types and blows up on an empty FileField."""
    return Source.objects.create(type=Source.IFRAME, name=url, url=url)


def entry(playlist, source, number=1, duration=None):
    return PlaylistEntry.objects.create(
        playlist=playlist, number=number, source=source, duration=duration)


class RenderPlaylistJsonTests(TestCase):
    def setUp(self):
        # Two entries so the single-item hold (asserted separately below) does
        # not overwrite these durations.
        self.base = Playlist.objects.create(name="base", default_duration=10)
        self.b1 = web_source("http://e/b1")
        entry(self.base, self.b1, number=1, duration=7)
        entry(self.base, web_source("http://e/b2"), number=2)

        self.logo = Playlist.objects.create(name="logo", default_duration=4)
        entry(self.logo, web_source("http://e/logo"))

        self.room = Playlist.objects.create(name="room", default_duration=6)
        entry(self.room, web_source("http://e/room"))

        self.schedule = Schedule.objects.create(name="s", default_playlist=self.base)
        self.screen = Screen.objects.create(name="scr", ip="10.0.0.9", schedule=self.schedule)

    def test_a_bare_playlist_reports_both_streams_as_null(self):
        out = render_playlist_json(self.base)
        self.assertEqual(out["interspersed"], {"playlist": None, "screen": None})
        self.assertEqual(out["playlist"],
                         [{"src": "http://e/b1", "type": "FRM", "duration": 7},
                          {"src": "http://e/b2", "type": "FRM", "duration": 10}])
        self.assertEqual(out["current_playlist"], self.base.pk)
        self.assertIsNone(out["screen_id"])

    def test_playlist_level_stream(self):
        self.base.interspersed_playlist = self.logo
        self.base.interspersed_rate = 3
        self.base.save()
        out = render_playlist_json(self.base)
        self.assertEqual(out["interspersed"]["playlist"],
                         {"items": [{"src": "http://e/logo", "type": "FRM", "duration": 4}],
                          "rate": 3})
        self.assertIsNone(out["interspersed"]["screen"])

    def test_screen_level_stream_is_independent_of_the_playlist_one(self):
        self.base.interspersed_playlist = self.logo
        self.base.interspersed_rate = 2
        self.base.save()
        self.screen.interspersed_playlist = self.room
        self.screen.interspersed_rate = 5
        self.screen.save()
        out = render_playlist_json(self.base, screen=self.screen, screen_id=self.screen.pk)
        self.assertEqual(out["interspersed"]["screen"],
                         {"items": [{"src": "http://e/room", "type": "FRM", "duration": 6}],
                          "rate": 5})
        self.assertEqual(out["interspersed"]["playlist"]["rate"], 2)
        self.assertEqual(out["screen_id"], self.screen.pk)

    def test_an_empty_interspersed_playlist_serialises_as_null(self):
        """Not {} and not {"items": []} — either would black out the player."""
        self.base.interspersed_playlist = Playlist.objects.create(name="empty")
        self.base.save()
        self.assertIsNone(render_playlist_json(self.base)["interspersed"]["playlist"])

    def test_an_interspersed_playlist_of_expired_content_serialises_as_null(self):
        expired = Playlist.objects.create(name="expired")
        source = web_source("http://e/gone")
        source.expires_at = datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc)
        source.save()
        entry(expired, source)
        self.base.interspersed_playlist = expired
        self.base.save()
        self.assertIsNone(render_playlist_json(self.base)["interspersed"]["playlist"])

    def test_a_rate_of_zero_is_clamped_to_one(self):
        """Mirrors the player's own Math.max(1, rate || 1)."""
        self.base.interspersed_playlist = self.logo
        self.base.interspersed_rate = 0
        self.base.save()
        self.assertEqual(render_playlist_json(self.base)["interspersed"]["playlist"]["rate"], 1)

    def test_interspersed_items_never_get_the_single_item_hold(self):
        self.base.interspersed_playlist = self.logo
        self.base.save()
        item = render_playlist_json(self.base)["interspersed"]["playlist"]["items"][0]
        self.assertEqual(item["duration"], 4)

    def test_the_single_item_hold_drops_when_a_stream_exists(self):
        """A lone base item is no longer replaced by itself, so holding it for
        an hour between logos would be wrong."""
        lone = Playlist.objects.create(name="lone", default_duration=8)
        entry(lone, web_source("http://e/lone"))
        self.assertEqual(
            render_playlist_json(lone)["playlist"][0]["duration"], SINGLE_ITEM_HOLD_SECONDS)

        lone.interspersed_playlist = self.logo
        lone.save()
        self.assertEqual(render_playlist_json(lone)["playlist"][0]["duration"], 8)

    def test_the_timestamp_follows_the_newest_interspersed_playlist(self):
        self.base.interspersed_playlist = self.logo
        self.base.save()
        before = render_last_updated(self.base)

        later = datetime.datetime.fromisoformat("2030-01-01T00:00:00+00:00")
        with time_machine.travel(later, tick=False):
            self.logo.meta_times_touch()
        self.logo.refresh_from_db()

        self.assertNotEqual(render_last_updated(self.base), before)
        self.assertEqual(render_last_updated(self.base), self.logo.last_updated.isoformat())

    def test_pointing_a_screen_at_an_older_playlist_still_republishes(self):
        """The case a plain max() over playlist timestamps cannot see.

        The room playlist is older than the base, so without Screen's own
        interspersed_last_updated the aggregate would not move and no device
        would ever refetch.
        """
        old = datetime.datetime.fromisoformat("2020-01-01T00:00:00+00:00")
        mid = datetime.datetime.fromisoformat("2021-01-01T00:00:00+00:00")
        later = datetime.datetime.fromisoformat("2030-01-01T00:00:00+00:00")

        with time_machine.travel(old, tick=False):
            self.room.meta_times_touch()
        with time_machine.travel(mid, tick=False):
            self.base.meta_times_touch()
        # Set directly so the pre_save receiver does not stamp it for us.
        Screen.objects.filter(pk=self.screen.pk).update(interspersed_last_updated=old)
        self.base.refresh_from_db()
        self.room.refresh_from_db()
        self.screen.refresh_from_db()

        # The base is the newest playlist, so a max() over playlist timestamps
        # alone would not move when the screen is pointed at the older one.
        self.assertGreater(self.base.last_updated, self.room.last_updated)
        before = render_last_updated(self.base, self.screen)
        self.assertEqual(before, self.base.last_updated.isoformat())

        with time_machine.travel(later, tick=False):
            self.screen.interspersed_playlist = self.room
            self.screen.save()
        self.screen.refresh_from_db()

        self.assertNotEqual(render_last_updated(self.base, self.screen), before)

    def test_changing_the_rate_republishes(self):
        before = render_last_updated(self.base, self.screen)
        later = datetime.datetime.fromisoformat("2030-01-01T00:00:00+00:00")
        with time_machine.travel(later, tick=False):
            self.screen.interspersed_rate = 4
            self.screen.save()
        self.screen.refresh_from_db()
        self.assertNotEqual(render_last_updated(self.base, self.screen), before)

    def test_renaming_a_screen_does_not_republish(self):
        before = render_last_updated(self.base, self.screen)
        later = datetime.datetime.fromisoformat("2030-01-01T00:00:00+00:00")
        with time_machine.travel(later, tick=False):
            self.screen.name = "renamed"
            self.screen.save()
        self.screen.refresh_from_db()
        self.assertEqual(render_last_updated(self.base, self.screen), before)

    def test_deleting_an_interspersed_playlist_republishes_its_referrers(self):
        """SET_NULL is a bulk UPDATE: no signals, no auto_now, no republish."""
        self.base.interspersed_playlist = self.logo
        self.base.save()
        self.screen.interspersed_playlist = self.logo
        self.screen.save()
        self.base.refresh_from_db()
        self.screen.refresh_from_db()
        before_playlist = self.base.last_updated
        before_screen = self.screen.interspersed_last_updated

        later = datetime.datetime.fromisoformat("2030-01-01T00:00:00+00:00")
        with time_machine.travel(later, tick=False):
            self.logo.delete()

        self.base.refresh_from_db()
        self.screen.refresh_from_db()
        self.assertGreater(self.base.last_updated, before_playlist)
        self.assertGreater(self.screen.interspersed_last_updated, before_screen)


@override_settings(IP_ACCESS_CONTROL_ENABLED=False)
class PlayerEndpointTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.base = Playlist.objects.create(name="base")
        entry(self.base, web_source("http://e/b1"))
        self.logo = Playlist.objects.create(name="logo")
        entry(self.logo, web_source("http://e/logo"))

        self.schedule = Schedule.objects.create(name="s", default_playlist=self.base)
        self.screen = Screen.objects.create(name="scr", ip="10.0.0.9", schedule=self.schedule,
                                            interspersed_playlist=self.logo)

    def test_screen_json_and_meta_report_the_same_timestamp(self):
        screen_json = self.client.get(f"/api/screen/{self.screen.pk}").json()
        meta = self.client.get(f"/api/meta/{self.screen.pk}").json()
        self.assertEqual(screen_json["playlist_last_updated"], meta["playlist_last_updated"])
        self.assertEqual(screen_json["current_playlist"], meta["current_playlist"])

    def test_polling_meta_twice_reports_the_same_timestamp(self):
        """Guards against a screen field that stamps itself on every heartbeat:
        the player would remount every minute and restart from item one."""
        first = self.client.get(f"/api/meta/{self.screen.pk}").json()
        second = self.client.get(f"/api/meta/{self.screen.pk}").json()
        self.assertEqual(first["playlist_last_updated"], second["playlist_last_updated"])

    def test_screen_json_carries_the_screen_stream(self):
        out = self.client.get(f"/api/screen/{self.screen.pk}").json()
        self.assertEqual(out["interspersed"]["screen"]["items"],
                         [{"src": "http://e/logo", "type": "FRM", "duration": 10}])

    def test_the_playlist_endpoint_reports_no_screen_stream(self):
        out = self.client.get(f"/api/playlist/{self.base.pk}").json()
        self.assertIsNone(out["interspersed"]["screen"])

    def test_the_ticker_payload_uses_the_new_interspersed_shape(self):
        self.screen.ticker_enabled = True
        self.screen.ticker_text = "closing at 6"
        self.screen.save()
        out = self.client.get(f"/api/screen/{self.screen.pk}").json()
        self.assertEqual(out["interspersed"], {"playlist": None, "screen": None})

    @override_settings(AUTO_MAKE_SCREENS_FOR_NEW_IPS=False)
    def test_the_unconfigured_payload_uses_the_new_interspersed_shape(self):
        Screen.objects.all().delete()
        out = self.client.get("/api/screen/").json()
        self.assertEqual(out["interspersed"], {"playlist": None, "screen": None})
