"""The Screens changelist filters: team scoping, and filtering by status."""

from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from estate.models import Building, Campus, Room
from estate.tests.helpers import grant_all_locations
from screens.models import Playlist, Schedule, Screen, ScreenStatus, Team
from screens.models.screen import ATTENTION_WINDOW


class ScreenListFilterTests(TestCase):
    def setUp(self):
        Team.objects.all().delete()
        self.team_a = Team.objects.create(name="Alpha")
        self.team_b = Team.objects.create(name="Bravo")

        self.user_a = User.objects.create_user('alice', 'a@x', 'pw', is_staff=True)
        grant_all_locations(self.user_a)
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

    # --- Status filter -------------------------------------------------------

    def test_status_filter_is_offered(self):
        resp = self._changelist()
        self.assertContains(resp, "By status")

    def test_filter_online(self):
        resp = self._changelist(status=ScreenStatus.ONLINE)
        self.assertEqual({s.name for s in self._rows(resp)}, {"screenAlpha"})

    def test_filter_offline(self):
        resp = self._changelist(status=ScreenStatus.OFFLINE)
        self.assertEqual({s.name for s in self._rows(resp)}, {"screenAlphaDark"})

    def test_filter_needs_attention(self):
        """A screen answering ping but not reporting is amber, not red."""
        Screen.objects.filter(pk=self.screen_a_off.pk).update(
            last_ping_ok=timezone.now(), last_ping_attempt=timezone.now())
        self.assertEqual(
            {s.name for s in self._rows(self._changelist(status=ScreenStatus.ATTENTION))},
            {"screenAlphaDark"})
        self.assertEqual(
            list(self._rows(self._changelist(status=ScreenStatus.OFFLINE))), [])

    def test_unfiltered_shows_both_and_still_excludes_other_teams(self):
        resp = self._changelist()
        self.assertEqual(
            {s.name for s in self._rows(resp)}, {"screenAlpha", "screenAlphaDark"})

    def test_status_filter_agrees_with_the_status_column(self):
        """The filter and Screen.status() must never disagree about a screen.

        They are built from the same tiers -- this is the test that would catch
        the SQL and the Python halves drifting apart.
        """
        Screen.objects.filter(pk=self.screen_a_off.pk).update(
            last_ping_ok=timezone.now(), last_ping_attempt=timezone.now())
        seen = set()
        for value in ScreenStatus.values:
            for screen in self._rows(self._changelist(status=value)):
                seen.add(value)
                self.assertEqual(screen.status(), value, screen.name)
        self.assertEqual(seen, {ScreenStatus.ONLINE, ScreenStatus.ATTENTION})

    def test_status_filter_composes_with_the_schedule_filter(self):
        resp = self._changelist(
            schedule__id__exact=str(self.sched_a.pk), status=ScreenStatus.OFFLINE)
        self.assertEqual({s.name for s in self._rows(resp)}, {"screenAlphaDark"})

    def test_a_screen_on_the_boundary_counts_as_offline(self):
        Screen.objects.filter(pk=self.screen_a.pk).update(
            last_seen=Screen.online_cutoff() - ATTENTION_WINDOW)
        self.assertNotIn(
            "screenAlpha",
            {s.name for s in self._rows(self._changelist(status=ScreenStatus.ONLINE))})
        self.assertIn(
            "screenAlpha",
            {s.name for s in self._rows(self._changelist(status=ScreenStatus.OFFLINE))})

    def test_the_changelist_renders_the_badge_and_its_reason(self):
        """The reason is what makes amber actionable, so it has to reach the
        page — a badge on its own tells nobody where to go."""
        Screen.objects.filter(pk=self.screen_a_off.pk).update(
            last_ping_ok=timezone.now(), last_ping_attempt=timezone.now())
        resp = self._changelist()
        self.assertContains(resp, "Online")
        self.assertContains(resp, "Needs attention")
        self.assertContains(resp, "Responds to ping but is not reporting")

    def test_the_display_methods_work_on_an_unannotated_screen(self):
        """ScreenAdmin always annotates, but the fallback has to hold: a bare
        Screen reaching a display method must render the same answer, not
        raise."""
        from screens.admin import ScreenAdmin
        admin_obj = ScreenAdmin(Screen, admin.site)
        Screen.objects.filter(pk=self.screen_a_off.pk).update(
            last_ping_ok=timezone.now(), last_ping_attempt=timezone.now())

        bare = Screen.objects.get(pk=self.screen_a_off.pk)
        annotated = Screen.objects.with_status().get(pk=self.screen_a_off.pk)

        self.assertEqual(admin_obj.show_status(bare), "Needs attention")
        self.assertEqual(admin_obj.show_status(bare), admin_obj.show_status(annotated))
        self.assertIn("Responds to ping", admin_obj.show_status_detail(bare))

    def test_a_screen_just_past_the_online_cutoff_is_amber_not_red(self):
        """The grace tier, which needs no probe: one missed poll is not death."""
        Screen.objects.filter(pk=self.screen_a.pk).update(
            last_seen=Screen.online_cutoff() - timedelta(seconds=1))
        self.assertIn(
            "screenAlpha",
            {s.name for s in self._rows(self._changelist(status=ScreenStatus.ATTENTION))})


class EstateFilterTests(TestCase):
    """Campus and building filters, which carry the schedule filter's trap twice over.

    The estate mirror holds every room in the university, so a stock
    RelatedFieldListFilter here would offer hundreds of buildings, almost all
    matching nothing — the bug already fixed for `schedule`, an order of
    magnitude worse.

    The fixture is arranged so both filters have two options for Alpha, since
    Django hides a related filter with one option or none:

        Central          Appleton Tower      Alpha's screen
                         Informatics Forum   Bravo's screen only
        King's Buildings JCMB                Alpha's screen
                         Swann               no screens at all
    """

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

        playlist = Playlist.objects.create(name="listA")
        playlist.teams.add(self.team_a)
        self.schedule = Schedule.objects.create(name="s", default_playlist=playlist)
        self.schedule.teams.add(self.team_a, self.team_b)

        self.central = Campus.objects.create(name="Central")
        self.kb = Campus.objects.create(name="Kings Buildings")
        self.appleton = self._building("Appleton Tower", self.central)
        self.forum = self._building("Informatics Forum", self.central)
        self.jcmb = self._building("JCMB", self.kb)
        self.swann = self._building("Swann Building", self.kb)

        self.lt2 = Room.objects.create(lsd_id="r1", name="LT2", building=self.appleton)
        self.g07 = Room.objects.create(lsd_id="r2", name="G.07", building=self.forum)
        self.lt_a = Room.objects.create(lsd_id="r3", name="Lecture A", building=self.jcmb)
        # No screen anywhere in Swann, and none in this JCMB room.
        Room.objects.create(lsd_id="r4", name="Seminar 1", building=self.swann)

        self.screen_at = self._screen("screenAppleton", "10.0.0.1", self.team_a, self.lt2)
        self.screen_jcmb = self._screen("screenJcmb", "10.0.0.2", self.team_a, self.lt_a)
        self.screen_unplaced = self._screen("screenUnplaced", "10.0.0.3", self.team_a, None)
        self.screen_bravo = self._screen("screenBravo", "10.0.0.4", self.team_b, self.g07)

        self.client_a = Client()
        self.client_a.force_login(self.user_a)

    def _building(self, name, campus):
        # Keyed the way estate.sync keys them: campus and name.
        return Building.objects.create(
            key=f"{campus.name}|{name}".casefold(), name=name, campus=campus)

    def _screen(self, name, ip, team, room):
        screen = Screen.objects.create(
            name=name, ip=ip, schedule=self.schedule, room=room)
        screen.teams.add(team)
        return screen

    def _changelist(self, client=None, **params):
        return (client or self.client_a).get('/admin/screens/screen/', params)

    def _rows(self, response):
        return response.context['cl'].result_list

    def _filter_choices(self, response, title):
        """The option labels of one filter."""
        cl = response.context['cl']
        for spec in cl.filter_specs:
            if spec.title == title:
                return [str(c['display']) for c in spec.choices(cl)]
        return None

    def assertOffered(self, choices, name):
        self.assertTrue(any(name in c for c in choices),
                        f"{name!r} not offered; got {choices!r}")

    def assertNotOffered(self, choices, name):
        self.assertFalse(any(name in c for c in choices),
                         f"{name!r} should not be offered; got {choices!r}")

    # --- option scoping -----------------------------------------------------

    def test_building_filter_offers_the_buildings_holding_your_screens(self):
        choices = self._filter_choices(self._changelist(), "building")
        self.assertOffered(choices, "Appleton Tower")
        self.assertOffered(choices, "JCMB")

    def test_building_filter_omits_a_building_holding_only_another_teams_screen(self):
        self.assertNotOffered(
            self._filter_choices(self._changelist(), "building"), "Informatics Forum")

    def test_building_filter_omits_a_building_with_no_screens_at_all(self):
        """The estate is mostly buildings nobody has a screen in."""
        self.assertNotOffered(
            self._filter_choices(self._changelist(), "building"), "Swann Building")

    def test_a_superuser_across_all_teams_is_offered_the_other_teams_building(self):
        c = Client()
        c.force_login(self.super)
        c.get('/admin/screens/screen/')
        choices = self._filter_choices(self._changelist(client=c), "building")
        self.assertOffered(choices, "Appleton Tower")
        self.assertOffered(choices, "Informatics Forum")
        self.assertNotOffered(choices, "Swann Building")

    def test_the_campus_filter_scopes_through_two_levels(self):
        choices = self._filter_choices(self._changelist(), "campus")
        self.assertOffered(choices, "Central")
        self.assertOffered(choices, "Kings Buildings")

    def test_the_filters_are_titled_apart_from_the_room_schedules_ones(self):
        resp = self._changelist()
        self.assertContains(resp, "By campus")
        self.assertContains(resp, "By building")

    # --- filtering ----------------------------------------------------------

    def test_filtering_by_building_returns_only_its_screens(self):
        resp = self._changelist(room__building__id__exact=str(self.appleton.pk))
        self.assertEqual({s.name for s in self._rows(resp)}, {"screenAppleton"})

    def test_another_teams_building_id_yields_nothing(self):
        resp = self._changelist(room__building__id__exact=str(self.forum.pk))
        self.assertEqual(list(self._rows(resp)), [])

    def test_filtering_by_campus_returns_its_screens(self):
        resp = self._changelist(
            room__building__campus__id__exact=str(self.central.pk))
        self.assertEqual({s.name for s in self._rows(resp)}, {"screenAppleton"})

    def test_the_room_set_filter_finds_screens_with_no_location(self):
        resp = self._changelist(room_set="no")
        self.assertEqual({s.name for s in self._rows(resp)}, {"screenUnplaced"})

    def test_the_room_set_filter_finds_screens_with_one(self):
        resp = self._changelist(room_set="yes")
        self.assertEqual(
            {s.name for s in self._rows(resp)}, {"screenAppleton", "screenJcmb"})

    def test_the_room_set_filter_finds_screens_in_an_inactive_room(self):
        """The datastore says the room is not open today."""
        Room.objects.filter(pk=self.lt_a.pk).update(active=False)
        resp = self._changelist(room_set="inactive")
        self.assertEqual({s.name for s in self._rows(resp)}, {"screenJcmb"})

    def test_the_inactive_room_filter_stays_team_scoped(self):
        Room.objects.filter(pk=self.g07.pk).update(active=False)
        resp = self._changelist(room_set="inactive")
        self.assertEqual(list(self._rows(resp)), [])

    def test_the_room_filter_offers_the_inactive_option(self):
        self.assertOffered(
            self._filter_choices(self._changelist(), "room"), "In an inactive room")

    def test_the_estate_filters_compose_with_the_status_filter(self):
        Screen.objects.filter(pk=self.screen_at.pk).update(
            last_seen=timezone.now() - timedelta(hours=2))
        resp = self._changelist(
            room__building__id__exact=str(self.appleton.pk),
            status=ScreenStatus.OFFLINE)
        self.assertEqual({s.name for s in self._rows(resp)}, {"screenAppleton"})
        empty = self._changelist(
            room__building__id__exact=str(self.appleton.pk),
            status=ScreenStatus.ONLINE)
        self.assertEqual(list(self._rows(empty)), [])

    def test_a_selected_building_still_filters_when_only_one_is_on_offer(self):
        """The trap behind the "Open in screen list" link.

        Django pops a filter's lookup parameter whether or not the filter
        survives has_output(), so with one building in scope the stock filter
        would hide *and* silently ignore the parameter, showing every screen.
        """
        Screen.objects.filter(pk=self.screen_jcmb.pk).update(room=None)
        resp = self._changelist(room__building__id__exact=str(self.appleton.pk))
        self.assertEqual({s.name for s in self._rows(resp)}, {"screenAppleton"})

    # --- building narrowed by campus ---------------------------------------

    def _choice_query(self, response, title, display):
        """The query string one filter option links to."""
        cl = response.context['cl']
        spec = next(s for s in cl.filter_specs if s.title == title)
        return next(c['query_string'] for c in spec.choices(cl)
                    if display in str(c['display']))

    def test_a_selected_campus_narrows_the_building_filter_to_it(self):
        choices = self._filter_choices(
            self._changelist(room__building__campus__id__exact=str(self.central.pk)),
            "building")
        self.assertOffered(choices, "Appleton Tower")
        self.assertNotOffered(choices, "JCMB")

    def test_the_narrowed_building_filter_stays_team_scoped(self):
        """Informatics Forum is on the selected campus, but holds only Bravo's screen."""
        choices = self._filter_choices(
            self._changelist(room__building__campus__id__exact=str(self.central.pk)),
            "building")
        self.assertNotOffered(choices, "Informatics Forum")

    def test_a_campus_with_one_screened_building_still_shows_the_building_filter(self):
        """Hiding it there would read as the filter breaking on selection."""
        resp = self._changelist(room__building__campus__id__exact=str(self.kb.pk))
        choices = self._filter_choices(resp, "building")
        self.assertIsNotNone(choices)
        self.assertOffered(choices, "JCMB")
        self.assertNotOffered(choices, "Appleton Tower")

    def test_a_junk_campus_value_does_not_break_the_page(self):
        resp = self._changelist(room__building__campus__id__exact="nope")
        self.assertIn(resp.status_code, (200, 302))

    def test_switching_campus_drops_a_building_not_on_it(self):
        resp = self._changelist(room__building__id__exact=str(self.appleton.pk))
        self.assertNotIn("room__building__id__exact",
                         self._choice_query(resp, "campus", "Kings Buildings"))

    def test_choosing_the_selected_buildings_own_campus_keeps_it(self):
        resp = self._changelist(room__building__id__exact=str(self.appleton.pk))
        self.assertIn(f"room__building__id__exact={self.appleton.pk}",
                      self._choice_query(resp, "campus", "Central"))

    def test_clearing_the_campus_keeps_the_building(self):
        resp = self._changelist(
            room__building__id__exact=str(self.appleton.pk),
            room__building__campus__id__exact=str(self.central.pk))
        self.assertIn(f"room__building__id__exact={self.appleton.pk}",
                      self._choice_query(resp, "campus", "All"))

    # --- support type -------------------------------------------------------

    def _set_support(self):
        Room.objects.filter(pk=self.lt2.pk).update(support_type="Central")
        Room.objects.filter(pk=self.g07.pk).update(support_type="CMVM")
        # lt_a keeps the default: no support type recorded.

    def test_the_support_filter_offers_your_screens_support_types(self):
        self._set_support()
        resp = self._changelist()
        self.assertContains(resp, "By support type")
        choices = self._filter_choices(resp, "support type")
        self.assertOffered(choices, "Central")
        self.assertOffered(choices, "Not recorded")

    def test_the_support_filter_omits_a_type_only_another_team_uses(self):
        self._set_support()
        self.assertNotOffered(
            self._filter_choices(self._changelist(), "support type"), "CMVM")

    def test_filtering_by_support_type(self):
        self._set_support()
        resp = self._changelist(support="Central")
        self.assertEqual({s.name for s in self._rows(resp)}, {"screenAppleton"})

    def test_filtering_by_no_support_type_excludes_screens_with_no_room(self):
        self._set_support()
        resp = self._changelist(support="_none")
        self.assertEqual({s.name for s in self._rows(resp)}, {"screenJcmb"})

    def test_another_teams_support_type_yields_nothing(self):
        self._set_support()
        self.assertEqual(list(self._rows(self._changelist(support="CMVM"))), [])

    def test_the_support_filter_is_hidden_with_no_support_types_recorded(self):
        self.assertNotContains(self._changelist(), "By support type")

    def test_a_selected_support_type_still_filters_when_none_is_on_offer(self):
        """The has_output() trap again: hidden must not mean ignored."""
        resp = self._changelist(support="Central")
        self.assertEqual(list(self._rows(resp)), [])

    def test_the_support_filter_composes_with_the_campus_filter(self):
        self._set_support()
        Room.objects.filter(pk=self.lt_a.pk).update(support_type="Central")
        resp = self._changelist(
            support="Central", room__building__campus__id__exact=str(self.kb.pk))
        self.assertEqual({s.name for s in self._rows(resp)}, {"screenJcmb"})

    # --- columns ------------------------------------------------------------

    def test_the_building_and_room_reach_the_changelist(self):
        resp = self._changelist()
        self.assertContains(resp, "Appleton Tower")
        self.assertContains(resp, "LT2")

    def test_a_screen_in_an_inactive_room_is_badged_in_the_room_column(self):
        Room.objects.filter(pk=self.lt_a.pk).update(active=False)
        resp = self._changelist()
        self.assertContains(resp, "Inactive", count=1)
        self.assertContains(resp, "Lecture A")

    def test_an_active_room_carries_no_badge(self):
        self.assertNotContains(self._changelist(), ">Inactive<")

    def test_the_room_name_is_still_escaped_inside_the_badged_cell(self):
        from screens.admin import ScreenAdmin
        Room.objects.filter(pk=self.lt_a.pk).update(
            active=False, name="<b>Lecture A</b>")
        cell = ScreenAdmin(Screen, admin.site).show_room(
            Screen.objects.select_related('room').get(pk=self.screen_jcmb.pk))
        self.assertIn("&lt;b&gt;Lecture A&lt;/b&gt;", cell)
        self.assertIn("Inactive", cell)

    def test_a_screen_with_no_room_renders_a_dash_rather_than_blank(self):
        from screens.admin import ScreenAdmin
        admin_obj = ScreenAdmin(Screen, admin.site)
        bare = Screen.objects.get(pk=self.screen_unplaced.pk)
        self.assertEqual(admin_obj.show_building(bare), "—")
        self.assertEqual(admin_obj.show_room(bare), "—")


class EstateFilterVisibilityTests(TestCase):
    """With no screen in any room, the estate filters hide themselves."""

    def setUp(self):
        Team.objects.all().delete()
        team = Team.objects.create(name="Alpha")
        user = User.objects.create_user('alice', 'a@x', 'pw', is_staff=True)
        grant_all_locations(user)
        user.teams.add(team)
        user.user_permissions.add(*Permission.objects.filter(
            content_type=ContentType.objects.get_for_model(Screen)))

        playlist = Playlist.objects.create(name="listA")
        playlist.teams.add(team)
        schedule = Schedule.objects.create(name="s", default_playlist=playlist)
        schedule.teams.add(team)
        screen = Screen.objects.create(name="unplaced", ip="10.0.0.1", schedule=schedule)
        screen.teams.add(team)

        # An estate exists; no screen is in it.
        campus = Campus.objects.create(name="Central")
        Building.objects.create(
            key="AT", name="Appleton Tower", campus=campus)

        self.client_a = Client()
        self.client_a.force_login(user)

    def test_an_estate_with_no_screens_in_it_offers_no_estate_filters(self):
        """RelatedFieldListFilter.has_output() is False with one option or none,
        so the feature is invisible until it has data."""
        resp = self.client_a.get('/admin/screens/screen/')
        self.assertNotContains(resp, "By building")
        self.assertNotContains(resp, "By campus")
        self.assertNotContains(resp, "Appleton Tower")

    def test_the_room_filter_is_still_offered(self):
        """It is the commissioning backlog, and useful precisely when empty."""
        resp = self.client_a.get('/admin/screens/screen/')
        self.assertContains(resp, "No room set")


class ChangelistQueryCountTests(TestCase):
    """list_select_related pins the row cost; it must not grow with the page."""

    def setUp(self):
        Team.objects.all().delete()
        self.team = Team.objects.create(name="Alpha")
        self.user = User.objects.create_user('alice', 'a@x', 'pw', is_staff=True)
        grant_all_locations(self.user)
        self.user.teams.add(self.team)
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type=ContentType.objects.get_for_model(Screen)))
        self.playlist = Playlist.objects.create(name="listA")
        self.playlist.teams.add(self.team)
        self.schedule = Schedule.objects.create(
            name="s", default_playlist=self.playlist)
        self.schedule.teams.add(self.team)

        campus = Campus.objects.create(name="Central")
        self.building = Building.objects.create(
            key="AT", name="Appleton Tower", campus=campus)

        self.client_a = Client()
        self.client_a.force_login(self.user)

    def _make_screens(self, n, start):
        for i in range(start, start + n):
            room = Room.objects.create(
                lsd_id=f"r{i}", name=f"Room {i}", building=self.building)
            screen = Screen.objects.create(
                name=f"screen{i}", ip=f"10.0.{i // 250}.{i % 250}",
                schedule=self.schedule, room=room)
            screen.teams.add(self.team)

    def test_the_query_count_does_not_grow_with_the_number_of_rows(self):
        self._make_screens(2, 0)
        self.client_a.get('/admin/screens/screen/')  # warm the session/team lookups
        with CaptureQueriesContext(connection) as few:
            self.client_a.get('/admin/screens/screen/')

        self._make_screens(6, 100)
        with CaptureQueriesContext(connection) as many:
            self.client_a.get('/admin/screens/screen/')

        # show_teams costs one query per row and predates this change; what
        # must not grow is the room/building lookup, so allow that one per
        # extra row and nothing more.
        self.assertLessEqual(len(many), len(few) + 6)
