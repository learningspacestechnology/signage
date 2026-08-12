import datetime
from django.core.exceptions import ValidationError
from django.test import TestCase

import time_machine
from django.db.models import ProtectedError

from screens.models import Playlist, PlaylistEntry, Source, PlaylistRelation
from screens.models.playlist import SINGLE_ITEM_HOLD_SECONDS

UTC = datetime.timezone.utc

def sources(playlist_entries):
    return list(map(lambda x: x.source, playlist_entries))


class PlaylistTests(TestCase):
    def setUp(self):
        self.base_time = datetime.datetime.fromisoformat("2022-03-27T20:59:34.000+00:00")
        traveller = time_machine.travel(self.base_time, tick=False)
        traveller.start()
        # Without this the frozen clock leaks into every later test class in the
        # process, where it silently collapses "before" and "after" timestamps.
        self.addCleanup(traveller.stop)
        self.list_a = Playlist.objects.create(name="listA")
        self.entry_a = PlaylistEntry.objects.create(playlist=self.list_a, number=1, source=Source.objects.create()).source
        self.list_b = Playlist.objects.create(name="listB")
        self.entry_b = PlaylistEntry.objects.create(playlist=self.list_b, number=2, source=Source.objects.create()).source
        self.list_c = Playlist.objects.create(name="listC")
        self.entry_c = PlaylistEntry.objects.create(playlist=self.list_c, number=3, source=Source.objects.create()).source

    def test_simple_list(self):
        self.assertListEqual(sources(self.list_a.get_sources()), [self.entry_a])

    def test_single_inherit(self):
        self.list_a.parents.add(self.list_b)
        self.assertListEqual(sources(self.list_a.get_sources()), [self.entry_a, self.entry_b])

    def test_deep_inherit(self):
        self.list_a.parents.add(self.list_b)
        self.list_b.parents.add(self.list_c)
        self.assertListEqual(sources(self.list_a.get_sources()), [self.entry_a, self.entry_b, self.entry_c])

    def test_multi_inherit(self):
        self.list_a.parents.add(self.list_b, self.list_c)
        self.assertListEqual(sources(self.list_a.get_sources()), [self.entry_a, self.entry_b, self.entry_c])

    def test_circular_doesnt_spin(self):
        self.list_a.parents.add(self.list_b)
        self.list_b.parents.add(self.list_a)
        self.assertListEqual(sources(self.list_a.get_sources()), [self.entry_a, self.entry_b])

    def test_deleting_a_parent_is_blocked(self):
        self.list_a.parents.add(self.list_b)
        self.assertRaises(ProtectedError, self.list_b.delete)
        self.list_a.delete()

    def test_time_locked_correctly(self):
        self.assertEqual(self.list_a.last_updated.astimezone(UTC), self.base_time.astimezone(UTC))

    def test_adding_a_source_updates_last_updated(self):
        update_time = datetime.datetime.fromisoformat("2022-03-28T21:59:34+00:00")
        time_machine.travel(update_time, tick=False).start()
        PlaylistEntry.objects.create(playlist=self.list_a, number=2, source=Source.objects.create())
        self.list_a.refresh_from_db()
        self.assertEqual(self.list_a.last_updated.astimezone(UTC), update_time.astimezone(UTC))

    def test_adding_a_parent_updates_last_updated(self):
        update_time = datetime.datetime.fromisoformat("2022-03-28T21:59:34+00:00")
        time_machine.travel(update_time, tick=False).start()
        PlaylistRelation.objects.create(inheriting_list=self.list_b, super_list=self.list_a)
        self.list_a.refresh_from_db()
        self.assertEqual(self.list_a.last_updated.astimezone(UTC), self.base_time.astimezone(UTC))
        self.list_b.refresh_from_db()
        self.assertEqual(self.list_b.last_updated.astimezone(UTC), update_time.astimezone(UTC))

    def test_adding_a_source_updates_childrens_last_updated(self):
        PlaylistRelation.objects.create(inheriting_list=self.list_b, super_list=self.list_a)
        update_time = datetime.datetime.fromisoformat("2022-03-28T21:59:34+00:00")
        time_machine.travel(update_time, tick=False).start()
        PlaylistEntry.objects.create(playlist=self.list_a, number=2, source=Source.objects.create())
        self.list_b.refresh_from_db()
        self.assertEqual(self.list_b.last_updated.astimezone(UTC), update_time.astimezone(UTC))

    def test_circular_parents_meta_times_update(self):
        self.list_a.parents.add(self.list_b)
        self.list_b.parents.add(self.list_a)
        self.list_a.meta_times_touch()

    def test_removing_a_parent_updates_last_updated(self):
        """Unlinking shrinks the child's content, so it has to republish too."""
        self.list_a.parents.add(self.list_b)
        update_time = datetime.datetime.fromisoformat("2022-03-28T21:59:34+00:00")
        time_machine.travel(update_time, tick=False).start()
        self.list_a.parents.remove(self.list_b)
        self.list_a.refresh_from_db()
        self.assertEqual(self.list_a.last_updated.astimezone(UTC), update_time.astimezone(UTC))


class InterspersedPlaylistTests(TestCase):
    def setUp(self):
        self.base = Playlist.objects.create(name="base", default_duration=17)
        self.base_source = PlaylistEntry.objects.create(
            playlist=self.base, number=1, source=Source.objects.create()).source
        self.logo = Playlist.objects.create(name="logo", default_duration=4)
        self.logo_source = PlaylistEntry.objects.create(
            playlist=self.logo, number=1, source=Source.objects.create()).source

    def test_interspersed_playlist_is_not_part_of_get_sources(self):
        self.base.interspersed_playlist = self.logo
        self.base.save()
        self.assertListEqual(sources(self.base.get_sources()), [self.base_source])

    def test_a_parents_interspersed_settings_are_ignored(self):
        """Interspersion is resolved one level deep and never inherited."""
        parent = Playlist.objects.create(name="parent")
        parent_source = PlaylistEntry.objects.create(
            playlist=parent, number=1, source=Source.objects.create()).source
        parent.interspersed_playlist = self.logo
        parent.save()
        self.base.parents.add(parent)
        self.assertListEqual(
            sources(self.base.get_sources()), [self.base_source, parent_source])

    def test_an_interspersed_playlist_in_the_parent_chain_still_resolves_fully(self):
        """The interspersed stream must not share the caller's cycle guard.

        With a shared block_list the logo playlist would be treated as already
        visited and silently resolve to nothing.
        """
        self.base.parents.add(self.logo)
        self.base.interspersed_playlist = self.logo
        self.base.save()
        self.assertListEqual(
            sources(self.base.get_sources()), [self.base_source, self.logo_source])
        self.assertListEqual(
            sources(self.base.interspersed_playlist.get_interspersed_sources()),
            [self.logo_source])

    def test_interspersed_sources_use_the_playlists_own_default_duration(self):
        self.assertEqual([e.duration for e in self.logo.get_interspersed_sources()], [4])

    def test_interspersed_sources_never_get_the_single_item_hold(self):
        """A one-item logo playlist would otherwise sit on screen for an hour."""
        self.assertNotEqual(
            self.logo.get_interspersed_sources()[0].duration, SINGLE_ITEM_HOLD_SECONDS)

    def test_an_explicit_entry_duration_survives(self):
        entry = self.logo.playlistentry_set.get()
        entry.duration = 5
        entry.save()
        self.assertEqual([e.duration for e in self.logo.get_interspersed_sources()], [5])

    def test_the_single_item_hold_still_applies_to_a_plain_playlist(self):
        self.assertEqual(
            self.base.get_resolved_sources()[0].duration, SINGLE_ITEM_HOLD_SECONDS)

    def test_a_source_in_both_lists_plays_in_both_roles(self):
        """The old model excluded the interspersed source from the rotation.

        That rule went with the single-source field: 'the same item' is no
        longer one identity now interspersed content is a whole playlist.
        """
        PlaylistEntry.objects.create(playlist=self.base, number=2, source=self.logo_source)
        self.base.interspersed_playlist = self.logo
        self.base.save()
        self.assertIn(self.logo_source, sources(self.base.get_sources()))
        self.assertIn(self.logo_source, sources(self.base.get_interspersed_sources()))

    def test_a_playlist_cannot_be_its_own_interspersed_playlist(self):
        self.base.teams.add(self.base.teams.model.objects.create(name="T"))
        self.base.interspersed_playlist = self.base
        with self.assertRaises(ValidationError):
            self.base.full_clean()
