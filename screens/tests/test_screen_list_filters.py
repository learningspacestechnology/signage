"""The Screens changelist filters: team scoping, and filtering by online status."""

from datetime import timedelta

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.utils import timezone

from screens.models import Playlist, Schedule, Screen, Team


class ScreenListFilterTests(TestCase):
    def setUp(self):
        Team.objects.all().delete()
        self.team_a = Team.objects.create(name="Alpha")
        self.team_b = Team.objects.create(name="Bravo")

        self.user_a = User.objects.create_user('alice', 'a@x', 'pw', is_staff=True)
        self.user_a.teams.add(self.team_a)
        ct = ContentType.objects.get_for_model(Screen)
        self.user_a.user_permissions.add(*Permission.objects.filter(content_type=ct))
        self.super = User.objects.create_superuser('root', 'r@x', 'pw')

        self.list_a = Playlist.objects.create(name="listA")
        self.list_a.teams.add(self.team_a)

        self.sched_a = Schedule.objects.create(
            name="scheduleAlpha", default_playlist=self.list_a)
        self.sched_a.teams.add(self.team_a)
        self.sched_b = Schedule.objects.create(
            name="scheduleBravo", default_playlist=self.list_a)
        self.sched_b.teams.add(self.team_b)
        # Alpha's, but on no screen -- so nothing to filter by.
        self.sched_a_unused = Schedule.objects.create(
            name="scheduleAlphaUnused", default_playlist=self.list_a)
        self.sched_a_unused.teams.add(self.team_a)

        self.screen_a = self._screen("screenAlpha", "10.0.0.1", self.sched_a,
                                     self.team_a, online=True)
        self.screen_a_off = self._screen("screenAlphaDark", "10.0.0.2", self.sched_a,
                                         self.team_a, online=False)
        self.screen_b = self._screen("screenBravo", "10.0.0.3", self.sched_b,
                                     self.team_b, online=True)

        self.client_a = Client()
        self.client_a.force_login(self.user_a)

    def _screen(self, name, ip, schedule, team, online):
        screen = Screen.objects.create(name=name, ip=ip, schedule=schedule)
        screen.teams.add(team)
        # last_seen is auto_now_add, so it has to be written past the auto value.
        seen = timezone.now() - (timedelta(seconds=5) if online else timedelta(hours=2))
        Screen.objects.filter(pk=screen.pk).update(last_seen=seen)
        screen.refresh_from_db()
        return screen

    def _changelist(self, client=None, **params):
        return (client or self.client_a).get('/admin/screens/screen/', params)

    def _rows(self, response):
        return response.context['cl'].result_list

    # --- Schedule filter scoping --------------------------------------------

    def test_schedule_filter_omits_other_teams_schedules(self):
        resp = self._changelist()
        self.assertContains(resp, "scheduleAlpha")
        self.assertNotContains(resp, "scheduleBravo")

    def test_schedule_filter_omits_own_schedules_with_no_screens(self):
        """RelatedOnly also drops options that could only ever match nothing."""
        resp = self._changelist()
        self.assertNotContains(resp, "scheduleAlphaUnused")

    def test_superuser_on_active_team_sees_only_that_teams_schedules(self):
        c = Client()
        c.force_login(self.super)
        c.get('/admin/screens/screen/')  # settle the active team (ALL_TEAMS)
        resp = self._changelist(client=c)
        # Superusers default to ALL_TEAMS, so both are in scope and on a screen.
        self.assertContains(resp, "scheduleAlpha")
        self.assertContains(resp, "scheduleBravo")

    def test_filtering_by_schedule_still_works(self):
        resp = self._changelist(schedule__id__exact=str(self.sched_a.pk))
        self.assertEqual(
            {s.name for s in self._rows(resp)}, {"screenAlpha", "screenAlphaDark"})

    def test_other_teams_schedule_id_yields_nothing(self):
        resp = self._changelist(schedule__id__exact=str(self.sched_b.pk))
        self.assertEqual(list(self._rows(resp)), [])

    # --- Online filter -------------------------------------------------------

    def test_online_filter_is_offered(self):
        resp = self._changelist()
        self.assertContains(resp, "By online status")

    def test_filter_online(self):
        resp = self._changelist(online='1')
        self.assertEqual({s.name for s in self._rows(resp)}, {"screenAlpha"})

    def test_filter_offline(self):
        resp = self._changelist(online='0')
        self.assertEqual({s.name for s in self._rows(resp)}, {"screenAlphaDark"})

    def test_unfiltered_shows_both_and_still_excludes_other_teams(self):
        resp = self._changelist()
        self.assertEqual(
            {s.name for s in self._rows(resp)}, {"screenAlpha", "screenAlphaDark"})

    def test_online_filter_agrees_with_the_online_column(self):
        """The filter and Screen.online() must never disagree about a screen."""
        for value, expected in (('1', True), ('0', False)):
            rows = self._rows(self._changelist(online=value))
            self.assertTrue(rows, f"no rows for online={value}")
            for screen in rows:
                self.assertEqual(bool(screen.online()), expected, screen.name)

    def test_online_filter_composes_with_the_schedule_filter(self):
        resp = self._changelist(
            schedule__id__exact=str(self.sched_a.pk), online='0')
        self.assertEqual({s.name for s in self._rows(resp)}, {"screenAlphaDark"})

    def test_a_screen_on_the_boundary_counts_as_offline(self):
        Screen.objects.filter(pk=self.screen_a.pk).update(
            last_seen=Screen.online_cutoff() - timedelta(seconds=1))
        self.assertNotIn(
            "screenAlpha", {s.name for s in self._rows(self._changelist(online='1'))})
        self.assertIn(
            "screenAlpha", {s.name for s in self._rows(self._changelist(online='0'))})
