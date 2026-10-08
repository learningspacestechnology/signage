"""Screen.last_updated is the screen half of the publish signal.

auto_now means every full save() republishes the screen. The 60-second heartbeat
is the one write that must not, and it is kept off by _get_meta saving with
update_fields=["last_seen"]. That exclusion is Django's own behaviour, not ours
-- Model._save_table filters the field list by update_fields *before* calling
field.pre_save() -- so it is pinned here at the model level as well as through
the endpoint, and a refactor of _get_meta cannot quietly reintroduce a
once-a-minute remount of every screen in the estate.
"""
import datetime

import time_machine
from django.test import TestCase
from django.utils import timezone

from screens.models import Playlist, Schedule, Screen

LATER = datetime.datetime.fromisoformat("2030-01-01T00:00:00+00:00")


class ScreenPublishTimestampTests(TestCase):
    def setUp(self):
        playlist = Playlist.objects.create(name="base")
        schedule = Schedule.objects.create(name="s", default_playlist=playlist)
        self.screen = Screen.objects.create(
            name="scr", ip="10.0.0.9", schedule=schedule)
        self.screen.refresh_from_db()
        self.created_at = self.screen.last_updated

    def test_a_heartbeat_save_leaves_the_publish_timestamp_alone(self):
        with time_machine.travel(LATER, tick=False):
            self.screen.last_seen = timezone.now()
            self.screen.save(update_fields=["last_seen"])

        self.assertEqual(self.screen.last_updated, self.created_at)  # in memory
        self.screen.refresh_from_db()
        self.assertEqual(self.screen.last_updated, self.created_at)  # and in the row
        self.assertEqual(self.screen.last_seen, LATER)  # the write did happen

    def test_a_plain_save_moves_the_publish_timestamp(self):
        """The other half of the pair. Without it, the test above would still
        pass if auto_now were dropped from the field altogether."""
        with time_machine.travel(LATER, tick=False):
            self.screen.save()
        self.screen.refresh_from_db()
        self.assertEqual(self.screen.last_updated, LATER)

    def test_a_queryset_update_does_not_stamp_it(self):
        """Why Playlist's pre_delete receiver passes last_updated explicitly:
        a queryset .update() never calls pre_save(), so auto_now cannot reach
        it. Without this, that explicit value reads as redundant."""
        with time_machine.travel(LATER, tick=False):
            Screen.objects.filter(pk=self.screen.pk).update(name="renamed")
        self.screen.refresh_from_db()
        self.assertEqual(self.screen.last_updated, self.created_at)


class ScreenBuildingTests(TestCase):
    """`building` is the room's whenever there is a room; alone otherwise."""

    def setUp(self):
        from estate.models import Building, Campus, Room

        campus = Campus.objects.create(name="Central")
        self.at = Building.objects.create(key="c|at", name="Appleton Tower",
                                          campus=campus)
        self.forum = Building.objects.create(key="c|if", name="Informatics Forum",
                                             campus=campus)
        self.lt2 = Room.objects.create(lsd_id="at-lt2", name="LT2", building=self.at)
        playlist = Playlist.objects.create(name="base")
        self.screen = Screen.objects.create(
            name="scr", ip="10.0.0.9",
            schedule=Schedule.objects.create(name="s", default_playlist=playlist))

    def test_a_room_sets_the_building(self):
        self.screen.room = self.lt2
        self.screen.save()
        self.screen.refresh_from_db()
        self.assertEqual(self.screen.building, self.at)

    def test_the_room_wins_over_a_disagreeing_building(self):
        self.screen.room, self.screen.building = self.lt2, self.forum
        self.screen.save()
        self.screen.refresh_from_db()
        self.assertEqual(self.screen.building, self.at)

    def test_a_building_alone_is_kept(self):
        self.screen.building = self.forum
        self.screen.save()
        self.screen.refresh_from_db()
        self.assertEqual(self.screen.building, self.forum)

    def test_saving_only_the_room_writes_the_building_too(self):
        self.screen.room = self.lt2
        self.screen.save(update_fields=["room"])
        self.screen.refresh_from_db()
        self.assertEqual(self.screen.building, self.at)

    def test_the_heartbeat_does_not_load_the_room(self):
        """One write, once a minute, for every device in the estate."""
        Screen.objects.filter(pk=self.screen.pk).update(room=self.lt2)
        screen = Screen.objects.get(pk=self.screen.pk)
        with self.assertNumQueries(1):
            screen.last_seen = timezone.now()
            screen.save(update_fields=["last_seen"])

    def test_the_migration_fills_the_building_from_the_room(self):
        from importlib import import_module

        from django.apps import apps

        Screen.objects.filter(pk=self.screen.pk).update(room=self.lt2, building=None)
        bare = Screen.objects.create(
            name="bare", ip="10.0.0.10", schedule=self.screen.schedule)

        import_module("screens.migrations.0038_screen_building").backfill_building(
            apps, None)

        self.screen.refresh_from_db()
        bare.refresh_from_db()
        self.assertEqual(self.screen.building, self.at)
        self.assertIsNone(bare.building)
