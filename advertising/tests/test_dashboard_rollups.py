"""The dashboard's estate rollup.

Read off the same team-scoped queryset and the same with_status() annotation as
the status doughnut, so the two cannot disagree — which is what most of this
asserts.
"""

from datetime import timedelta

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from estate.models import Building, Campus, Room
from estate.tests.helpers import grant_all_locations
from screens.models import Playlist, Schedule, Screen, Team


class DashboardRollupTests(TestCase):
    def setUp(self):
        Team.objects.all().delete()
        self.team_a = Team.objects.create(name="Alpha")
        self.team_b = Team.objects.create(name="Bravo")

        self.user_a = User.objects.create_user('alice', 'a@x', 'pw', is_staff=True)
        grant_all_locations(self.user_a)
        self.user_a.teams.add(self.team_a)
        self.user_a.user_permissions.add(*Permission.objects.filter(
            content_type=ContentType.objects.get_for_model(Screen)))
        self.super = User.objects.create_superuser('root', 'r@x', 'pw')

        playlist = Playlist.objects.create(name="p")
        playlist.teams.add(self.team_a)
        self.schedule = Schedule.objects.create(name="s", default_playlist=playlist)
        self.schedule.teams.add(self.team_a, self.team_b)

        campus = Campus.objects.create(name="Central")
        self.appleton = Building.objects.create(
            key="AT", name="Appleton Tower", campus=campus)
        self.forum = Building.objects.create(
            key="IF", name="Informatics Forum", campus=campus)

        self.client_a = Client()
        self.client_a.force_login(self.user_a)

    def _room(self, lsd_id, building):
        return Room.objects.create(lsd_id=lsd_id, name=lsd_id, building=building)

    def _screen(self, name, ip, team, room=None, online=True):
        screen = Screen.objects.create(
            name=name, ip=ip, schedule=self.schedule, room=room)
        screen.teams.add(team)
        if not online:
            Screen.objects.filter(pk=screen.pk).update(
                last_seen=timezone.now() - timedelta(hours=2))
        return screen

    def _dashboard(self, client=None):
        return (client or self.client_a).get(reverse('admin:index'))

    def _rows(self, client=None):
        return self._dashboard(client).context['screens_by_building']

    # --- the empty case, which is most sites -------------------------------

    def test_with_no_rooms_assigned_the_panel_is_absent(self):
        self._screen("unplaced", "10.0.0.1", self.team_a)
        resp = self._dashboard()
        self.assertEqual(resp.context['screens_by_building'], [])
        self.assertNotContains(resp, "Screens by building")

    # --- counts -------------------------------------------------------------

    def test_it_counts_each_status_per_building(self):
        self._screen("a1", "10.0.0.1", self.team_a, self._room("r1", self.appleton))
        self._screen("a2", "10.0.0.2", self.team_a, self._room("r2", self.appleton),
                     online=False)
        self._screen("f1", "10.0.0.3", self.team_a, self._room("r3", self.forum))

        rows = {r['name']: r for r in self._rows()}

        self.assertEqual(
            (rows["Appleton Tower"]['online'], rows["Appleton Tower"]['offline'],
             rows["Appleton Tower"]['total']),
            (1, 1, 2))
        self.assertEqual(rows["Informatics Forum"]['total'], 1)

    def test_the_counts_are_team_scoped(self):
        self._screen("a1", "10.0.0.1", self.team_a, self._room("r1", self.appleton))
        self._screen("b1", "10.0.0.2", self.team_b, self._room("r2", self.appleton))

        self.assertEqual(self._rows()[0]['total'], 1)

        client = Client()
        client.force_login(self.super)
        client.get(reverse('admin:index'))  # settle ALL_TEAMS
        self.assertEqual(self._rows(client)[0]['total'], 2)

    def test_the_rollup_totals_match_the_status_doughnut(self):
        """Two views of one queryset; they must never drift apart."""
        self._screen("a1", "10.0.0.1", self.team_a, self._room("r1", self.appleton))
        self._screen("a2", "10.0.0.2", self.team_a, self._room("r2", self.appleton),
                     online=False)
        self._screen("f1", "10.0.0.3", self.team_a, self._room("r3", self.forum),
                     online=False)

        context = self._dashboard().context
        rows = context['screens_by_building']

        self.assertEqual(sum(r['online'] for r in rows), context['screens_online'])
        self.assertEqual(sum(r['offline'] for r in rows), context['screens_offline'])
        self.assertEqual(
            sum(r['attention'] for r in rows), context['screens_attention'])

    def test_a_screen_with_no_room_is_counted_apart_not_in_a_building(self):
        self._screen("a1", "10.0.0.1", self.team_a, self._room("r1", self.appleton))
        self._screen("unplaced", "10.0.0.2", self.team_a)

        context = self._dashboard().context
        self.assertEqual(context['screens_without_location'], 1)
        self.assertEqual(sum(r['total'] for r in context['screens_by_building']), 1)

    def test_a_screen_in_a_building_with_no_room_counts_in_the_building(self):
        """Placed deliberately — a foyer — so not part of the backlog line."""
        foyer = self._screen("foyer", "10.0.0.1", self.team_a)
        Screen.objects.filter(pk=foyer.pk).update(building=self.appleton)

        context = self._dashboard().context
        self.assertEqual(context['screens_without_location'], 0)
        [row] = context['screens_by_building']
        self.assertEqual((row['name'], row['total']), ("Appleton Tower", 1))

    def test_the_unassigned_link_uses_the_filter_parameter_that_exists(self):
        self._screen("a1", "10.0.0.1", self.team_a, self._room("r1", self.appleton))
        self._screen("unplaced", "10.0.0.2", self.team_a)

        url = self._dashboard().context['screens_without_location_url']
        self.assertTrue(url.endswith("?room_set=no"))

        resp = self.client_a.get(url)
        self.assertEqual(
            {s.name for s in resp.context['cl'].result_list}, {"unplaced"})

    # --- ordering and truncation -------------------------------------------

    def test_the_worst_building_comes_first(self):
        self._screen("a1", "10.0.0.1", self.team_a, self._room("r1", self.appleton))
        self._screen("f1", "10.0.0.2", self.team_a, self._room("r2", self.forum),
                     online=False)

        self.assertEqual(
            [r['name'] for r in self._rows()],
            ["Informatics Forum", "Appleton Tower"])

    def test_the_list_is_capped_and_says_how_many_it_left_out(self):
        from advertising.admin import BUILDINGS_SHOWN

        for i in range(BUILDINGS_SHOWN + 2):
            building = Building.objects.create(
                key=f"B{i}", name=f"Building {i}",
                campus=self.appleton.campus)
            self._screen(f"s{i}", f"10.0.1.{i}", self.team_a,
                         self._room(f"x{i}", building))

        context = self._dashboard().context
        self.assertEqual(len(context['screens_by_building']), BUILDINGS_SHOWN)
        self.assertEqual(context['screens_by_building_more'], 2)

    # --- rendering ----------------------------------------------------------

    def test_each_count_carries_a_word_not_only_a_colour(self):
        self._screen("a1", "10.0.0.1", self.team_a, self._room("r1", self.appleton))
        self._screen("a2", "10.0.0.2", self.team_a, self._room("r2", self.appleton),
                     online=False)

        resp = self._dashboard()
        self.assertContains(resp, "1 online")
        self.assertContains(resp, "1 offline")

    def test_each_row_links_to_that_buildings_page(self):
        self._screen("a1", "10.0.0.1", self.team_a, self._room("r1", self.appleton))
        resp = self._dashboard()
        self.assertContains(
            resp,
            reverse('admin:estate_building_screens', args=[self.appleton.pk]))

    def test_the_footnote_says_the_counts_are_team_scoped(self):
        self._screen("a1", "10.0.0.1", self.team_a, self._room("r1", self.appleton))
        self.assertContains(self._dashboard(), "Counts cover screens in your teams.")
