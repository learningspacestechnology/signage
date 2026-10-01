"""The per-building screens page.

A page rather than a filtered changelist because it answers the question a
changelist structurally cannot: which rooms in this building are dark.
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


class BuildingScreensPageTests(TestCase):
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
        self.building = Building.objects.create(
            key="AT", name="Appleton Tower", campus=campus)

        self.lt2 = Room.objects.create(lsd_id="r1", name="LT2", building=self.building)
        self.lt3 = Room.objects.create(lsd_id="r2", name="LT3", building=self.building)
        self.dark = Room.objects.create(
            lsd_id="r3", name="Seminar 5", building=self.building, capacity=30)

        self.screen_a = self._screen("alphaScreen", "10.0.0.1", self.team_a, self.lt2)
        self.screen_b = self._screen("bravoScreen", "10.0.0.2", self.team_b, self.lt3)

        self.client_a = Client()
        self.client_a.force_login(self.user_a)

    def _screen(self, name, ip, team, room):
        screen = Screen.objects.create(
            name=name, ip=ip, schedule=self.schedule, room=room)
        screen.teams.add(team)
        return screen

    def _url(self, building=None):
        return reverse('admin:estate_building_screens',
                       args=[(building or self.building).pk])

    # --- scoping and access -------------------------------------------------

    def test_it_lists_your_teams_screens_in_the_building(self):
        resp = self.client_a.get(self._url())
        self.assertEqual(
            {s.name for s in resp.context['screens']}, {"alphaScreen"})

    def test_it_omits_another_teams_screen_in_the_same_building(self):
        self.assertNotContains(self.client_a.get(self._url()), "bravoScreen")

    def test_a_superuser_across_all_teams_sees_both(self):
        client = Client()
        client.force_login(self.super)
        client.get('/admin/')  # settle the active team
        resp = client.get(self._url())
        self.assertEqual(
            {s.name for s in resp.context['screens']},
            {"alphaScreen", "bravoScreen"})

    def test_it_is_refused_without_view_screen(self):
        """admin_view only enforces staff, so the content is gated explicitly."""
        user = User.objects.create_user('bob', 'b@x', 'pw', is_staff=True)
        grant_all_locations(user)
        user.teams.add(self.team_a)
        client = Client()
        client.force_login(user)
        self.assertEqual(client.get(self._url()).status_code, 403)

    def test_an_unknown_building_is_a_404(self):
        self.assertEqual(self.client_a.get(
            reverse('admin:estate_building_screens', args=[999999])).status_code, 404)

    def test_the_url_is_not_swallowed_by_the_admin_object_id_catch_all(self):
        """It resolves to this view, not to a legacy redirect to a change page."""
        resp = self.client_a.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.resolver_match.url_name, 'estate_building_screens')

    # --- content ------------------------------------------------------------

    def test_the_status_badge_agrees_with_the_screens_own_status(self):
        Screen.objects.filter(pk=self.screen_a.pk).update(
            last_seen=timezone.now() - timedelta(hours=2))
        resp = self.client_a.get(self._url())
        screen = resp.context['screens'][0]
        self.assertEqual(screen.derived_status, screen.status())
        self.assertContains(resp, "Offline")

    def test_the_reason_reaches_the_page_not_just_the_badge(self):
        """Amber is only actionable when it says why."""
        Screen.objects.filter(pk=self.screen_a.pk).update(
            last_seen=timezone.now() - timedelta(hours=2),
            last_ping_ok=timezone.now(), last_ping_attempt=timezone.now())
        resp = self.client_a.get(self._url())
        self.assertContains(resp, "Needs attention")
        self.assertContains(resp, "Responds to ping but is not reporting")

    def test_the_rollup_counts_match_the_listed_screens(self):
        Screen.objects.filter(pk=self.screen_a.pk).update(
            last_seen=timezone.now() - timedelta(hours=2))
        resp = self.client_a.get(self._url())
        self.assertEqual(
            (resp.context['online_count'], resp.context['attention_count'],
             resp.context['offline_count']),
            (0, 0, 1))

    # --- the panel a changelist could not produce ---------------------------

    def test_rooms_with_no_screen_are_listed(self):
        resp = self.client_a.get(self._url())
        self.assertEqual(
            {r.name for r in resp.context['dark_rooms']}, {"LT3", "Seminar 5"})

    def test_a_room_holding_your_own_screen_is_not_listed_as_dark(self):
        self.assertNotIn(
            "LT2", {r.name for r in self.client_a.get(self._url()).context['dark_rooms']})

    def test_the_panel_says_the_list_is_team_scoped(self):
        """LT3 holds Bravo's screen, so "no screen" would be a lie unqualified."""
        resp = self.client_a.get(self._url())
        self.assertContains(resp, "Rooms with no screen you can see")

    def test_a_fully_covered_building_shows_no_dark_panel(self):
        Room.objects.filter(pk__in=[self.lt3.pk, self.dark.pk]).delete()
        resp = self.client_a.get(self._url())
        self.assertEqual(list(resp.context['dark_rooms']), [])
        self.assertNotContains(resp, "Rooms with no screen you can see")

    # --- inactive rooms -----------------------------------------------------

    def test_a_screen_in_an_inactive_room_is_badged(self):
        Room.objects.filter(pk=self.lt2.pk).update(active=False)
        resp = self.client_a.get(self._url())
        self.assertContains(resp, "Inactive", count=1)

    def test_an_inactive_dark_room_is_listed_and_labelled_not_hidden(self):
        """A room that opens next month may rightly be waiting for a screen."""
        Room.objects.filter(pk=self.dark.pk).update(active=False)
        resp = self.client_a.get(self._url())
        self.assertIn("Seminar 5", {r.name for r in resp.context['dark_rooms']})
        self.assertContains(resp, "Inactive", count=1)

    def test_an_all_active_building_shows_no_badge(self):
        self.assertNotContains(self.client_a.get(self._url()), ">Inactive<")

    # --- links out ----------------------------------------------------------

    def test_it_links_to_the_changelist_filtered_by_this_building(self):
        resp = self.client_a.get(self._url())
        self.assertContains(
            resp, f"room__building__id__exact={self.building.pk}")

    def test_the_changelist_link_actually_filters(self):
        """Not a given: Django drops a lookup for a filter that does not render."""
        url = self.client_a.get(self._url()).context['changelist_url']
        resp = self.client_a.get(url)
        self.assertEqual(
            {s.name for s in resp.context['cl'].result_list}, {"alphaScreen"})

    def test_a_building_admin_row_links_here_only_when_it_has_screens(self):
        from django.contrib import admin as dj_admin
        from estate.admin import BuildingAdmin
        admin_obj = BuildingAdmin(Building, dj_admin.site)

        self.building.n_screens = 0
        self.assertEqual(admin_obj.screens_link(self.building), "—")

        self.building.n_screens = 3
        self.assertIn(self._url(), admin_obj.screens_link(self.building))
