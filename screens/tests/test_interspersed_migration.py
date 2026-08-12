"""The 0032 data conversion, exercised against a real migration run.

Brittle by nature — it pins a specific pair of migration states — but this is
the only step in the change that can silently damage live data, and it is
otherwise unexercised. If 0032 is ever squashed, delete this module rather than
trying to keep it limping.
"""
from django.db.migrations.executor import MigrationExecutor
from django.db import connection
from django.test import TransactionTestCase


class InterspersedMigrationTests(TransactionTestCase):
    migrate_from = [("screens", "0031_alter_screen_options")]
    migrate_to = [("screens", "0032_interspersed_playlists")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        executor.loader.build_graph()
        self.old_apps = executor.loader.project_state(self.migrate_from).apps

    def tearDown(self):
        # Leave the database at the latest state for whatever runs next.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)

    def run_migration(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        return executor.loader.project_state(self.migrate_to).apps

    def old(self, name):
        return self.old_apps.get_model("screens", name)

    def make_source(self, name):
        return self.old("Source").objects.create(
            type="FRM", name=name, url=f"http://e/{name}")

    def make_team(self, name):
        return self.old("Team").objects.create(name=name)

    def make_screen(self, name, source, teams=(), ip="10.0.0.1"):
        playlist = self.old("Playlist").objects.create(name=f"{name}-sched-list")
        schedule = self.old("Schedule").objects.create(
            name=f"{name}-sched", default_playlist=playlist)
        screen = self.old("Screen").objects.create(
            name=name, ip=ip, schedule=schedule, interspersed_source=source)
        screen.teams.add(*teams)
        return screen

    # --- Conversion ----------------------------------------------------------

    def test_an_interspersed_source_becomes_a_one_entry_playlist(self):
        team = self.make_team("Alpha")
        logo = self.make_source("logo")
        owner = self.old("Playlist").objects.create(name="foyer")
        owner.teams.add(team)
        owner.interspersed_source = logo
        owner.save()

        apps = self.run_migration()
        owner = apps.get_model("screens", "Playlist").objects.get(name="foyer")

        converted = owner.interspersed_playlist
        self.assertIsNotNone(converted)
        self.assertEqual(converted.name, "Interspersed: logo")
        self.assertEqual(owner.interspersed_rate, 1)
        # 10 is what the old serialiser effectively gave interspersed items.
        self.assertEqual(converted.default_duration, 10)

        entries = list(converted.playlistentry_set.all())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].source.name, "logo")
        self.assertIsNone(entries[0].duration)

    def test_a_source_used_twice_is_converted_once(self):
        team = self.make_team("Alpha")
        logo = self.make_source("logo")
        owner = self.old("Playlist").objects.create(name="foyer")
        owner.teams.add(team)
        owner.interspersed_source = logo
        owner.save()
        screen = self.make_screen("Foyer screen", logo, teams=[team])

        apps = self.run_migration()
        Playlist = apps.get_model("screens", "Playlist")
        Screen = apps.get_model("screens", "Screen")

        self.assertEqual(Playlist.objects.filter(name="Interspersed: logo").count(), 1)
        self.assertEqual(
            Playlist.objects.get(pk=owner.pk).interspersed_playlist_id,
            Screen.objects.get(pk=screen.pk).interspersed_playlist_id)

    def test_teams_are_unioned_across_every_referrer(self):
        team_a = self.make_team("Alpha")
        team_b = self.make_team("Bravo")
        logo = self.make_source("logo")
        owner = self.old("Playlist").objects.create(name="foyer")
        owner.teams.add(team_a)
        owner.interspersed_source = logo
        owner.save()
        self.make_screen("Foyer screen", logo, teams=[team_b])

        apps = self.run_migration()
        converted = apps.get_model("screens", "Playlist").objects.get(
            name="Interspersed: logo")
        self.assertEqual(
            set(converted.teams.values_list("name", flat=True)), {"Alpha", "Bravo"})

    def test_a_teamless_owner_falls_back_rather_than_leaving_it_orphaned(self):
        """Screens auto-created for unknown IPs have no teams, and a team-less
        playlist is invisible to every non-superuser and unfixable in the admin."""
        self.old("Team").objects.all().delete()
        logo = self.make_source("logo")
        self.make_screen("Auto screen", logo)

        apps = self.run_migration()
        converted = apps.get_model("screens", "Playlist").objects.get(
            name="Interspersed: logo")
        self.assertTrue(converted.teams.exists())

    def test_objects_without_interspersed_content_are_untouched(self):
        team = self.make_team("Alpha")
        plain = self.old("Playlist").objects.create(name="plain")
        plain.teams.add(team)

        apps = self.run_migration()
        Playlist = apps.get_model("screens", "Playlist")

        self.assertIsNone(Playlist.objects.get(pk=plain.pk).interspersed_playlist)
        self.assertFalse(Playlist.objects.filter(name__startswith="Interspersed: ").exists())

    def test_a_long_source_name_is_truncated(self):
        """Playlist.name is unbounded, but the admin log's object_repr is not."""
        team = self.make_team("Alpha")
        logo = self.make_source("x" * 400)
        owner = self.old("Playlist").objects.create(name="foyer")
        owner.teams.add(team)
        owner.interspersed_source = logo
        owner.save()

        apps = self.run_migration()
        converted = apps.get_model("screens", "Playlist").objects.get(pk=owner.pk)
        self.assertLessEqual(len(converted.interspersed_playlist.name), 150)
