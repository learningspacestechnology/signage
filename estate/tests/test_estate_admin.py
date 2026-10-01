"""The estate admin is a viewer over rows the nightly sync owns."""

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from estate.models import Building, Campus, Room
from estate.tests.helpers import grant_all_locations
from screens.models import Playlist, Schedule, Screen, Team


def _perms(model, *codenames):
    ct = ContentType.objects.get_for_model(model)
    qs = Permission.objects.filter(content_type=ct)
    return qs.filter(codename__in=codenames) if codenames else qs


class EstateAdminTestCase(TestCase):
    def setUp(self):
        Team.objects.all().delete()
        self.team = Team.objects.create(name="Alpha")
        self.campus = Campus.objects.create(name="Central")
        self.building = Building.objects.create(
            key="AT", name="Appleton Tower", campus=self.campus)
        self.room = Room.objects.create(
            lsd_id="r1", name="LT2", building=self.building, capacity=200)

    def _viewer(self, username="viewer"):
        user = User.objects.create_user(username, f'{username}@x', 'pw', is_staff=True)
        grant_all_locations(user)
        user.teams.add(self.team)
        for model in (Campus, Building, Room):
            user.user_permissions.add(
                *_perms(model, f'view_{model._meta.model_name}'))
        client = Client()
        client.force_login(user)
        return user, client


class ReadOnlyTests(EstateAdminTestCase):
    """Editing here would survive only until the next sync, so it is refused."""

    def test_a_viewer_can_read_the_changelists(self):
        _, client = self._viewer()
        for url in ('admin:estate_campus_changelist',
                    'admin:estate_building_changelist',
                    'admin:estate_room_changelist'):
            self.assertEqual(client.get(reverse(url)).status_code, 200, url)

    def test_even_a_superuser_cannot_add(self):
        """Superuser is the case that would otherwise slip through."""
        client = Client()
        client.force_login(User.objects.create_superuser('root', 'r@x', 'pw'))
        self.assertEqual(client.get(reverse('admin:estate_room_add')).status_code, 403)

    def test_even_a_superuser_cannot_change(self):
        client = Client()
        client.force_login(User.objects.create_superuser('root', 'r@x', 'pw'))
        url = reverse('admin:estate_room_change', args=[self.room.pk])

        self.assertEqual(
            client.post(url, {'name': 'Renamed', 'building': self.building.pk}).status_code,
            403)

        self.room.refresh_from_db()
        self.assertEqual(self.room.name, "LT2")

    def test_the_change_page_renders_read_only_rather_than_404(self):
        """The URL has to keep working -- the help hint slot hangs off it."""
        _, client = self._viewer()
        resp = client.get(reverse('admin:estate_room_change', args=[self.room.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'name="_save"')

    def test_no_delete_action_is_offered(self):
        _, client = self._viewer()
        resp = client.get(reverse('admin:estate_room_changelist'))
        self.assertNotContains(resp, 'delete_selected')


class ScreenCountTests(EstateAdminTestCase):
    """The Screens column is team-scoped, which is why it says so."""

    def setUp(self):
        super().setUp()
        self.other_team = Team.objects.create(name="Bravo")
        playlist = Playlist.objects.create(name="p")
        playlist.teams.add(self.team)
        self.schedule = Schedule.objects.create(name="s", default_playlist=playlist)
        self.schedule.teams.add(self.team, self.other_team)

        self.room_b = Room.objects.create(
            lsd_id="r2", name="LT3", building=self.building)
        for ip, room, team in (("10.0.0.1", self.room, self.team),
                               ("10.0.0.2", self.room_b, self.other_team)):
            screen = Screen.objects.create(
                name=f"screen {ip}", ip=ip, schedule=self.schedule, room=room)
            screen.teams.add(team)

    def _counts(self, client, url_name):
        cl = client.get(reverse(url_name)).context['cl']
        return {obj.name: obj.n_screens for obj in cl.result_list}

    def test_a_team_member_sees_only_their_own_screens_counted(self):
        _, client = self._viewer()
        self.assertEqual(
            self._counts(client, 'admin:estate_building_changelist'),
            {"Appleton Tower": 1})

    def test_a_superuser_across_all_teams_sees_them_all(self):
        client = Client()
        client.force_login(User.objects.create_superuser('root', 'r@x', 'pw'))
        client.get(reverse('admin:estate_building_changelist'))  # settle ALL_TEAMS
        self.assertEqual(
            self._counts(client, 'admin:estate_building_changelist'),
            {"Appleton Tower": 2})

    def test_the_column_says_the_number_is_team_scoped(self):
        _, client = self._viewer()
        resp = client.get(reverse('admin:estate_building_changelist'))
        self.assertContains(resp, "Screens (your teams)")

    def test_the_room_count_is_not_multiplied_by_the_screen_count(self):
        """Chained Count() aggregates cross-join; a Subquery does not."""
        _, client = self._viewer()
        cl = client.get(reverse('admin:estate_building_changelist')).context['cl']
        self.assertEqual([b.n_rooms for b in cl.result_list], [2])

    def test_a_campus_counts_its_buildings_and_rooms_independently(self):
        _, client = self._viewer()
        cl = client.get(reverse('admin:estate_campus_changelist')).context['cl']
        campus = cl.result_list[0]
        self.assertEqual((campus.n_buildings, campus.n_rooms), (1, 2))


class SyncButtonTests(EstateAdminTestCase):
    def test_the_room_list_offers_a_sync_button(self):
        _, client = self._viewer()
        resp = client.get(reverse('admin:estate_room_changelist'))
        self.assertContains(resp, "Sync estate now")
        self.assertContains(resp, reverse('admin:estate_sync_now'))

    def test_sync_now_refuses_a_get(self):
        """A GET would let a link prefetch or a refresh queue a run."""
        _, client = self._viewer()
        self.assertEqual(client.get(reverse('admin:estate_sync_now')).status_code, 405)


class SignageFieldsTests(EstateAdminTestCase):
    """The columns the signage feed brought: open-today and Estates codes."""

    def setUp(self):
        super().setUp()
        self.hub = Building.objects.create(
            key="HUB", name="40 George Sq Lower Hub", campus=self.campus)
        Room.objects.filter(pk=self.room.pk).update(building_code="0228")
        Room.objects.create(lsd_id="r2", name="G.01", building=self.hub,
                            building_code="0228", active=False)
        Room.objects.create(lsd_id="r3", name="G.02", building=self.hub,
                            building_code="0222")
        _, self.client = self._viewer()

    def test_an_estates_code_finds_every_building_it_spans_once_each(self):
        resp = self.client.get(
            reverse('admin:estate_building_changelist'), {'q': '0228'})
        self.assertEqual(
            sorted(b.name for b in resp.context['cl'].result_list),
            ["40 George Sq Lower Hub", "Appleton Tower"])

    def test_the_building_page_lists_the_codes_its_rooms_carry(self):
        resp = self.client.get(
            reverse('admin:estate_building_change', args=[self.hub.pk]))
        self.assertContains(resp, "0222, 0228")

    def _building_list(self, **params):
        return self.client.get(reverse('admin:estate_building_changelist'), params)

    def test_the_building_list_shows_each_buildings_codes(self):
        Building.objects.create(key="NMS", name="National Museum", campus=self.campus)
        cl = self._building_list().context['cl']
        self.assertEqual(
            {b.name: cl.model_admin.list_estates_codes(b) for b in cl.result_list},
            {"Appleton Tower": "0228", "40 George Sq Lower Hub": "0222, 0228",
             "National Museum": "—"})

    def test_the_codes_column_costs_one_query_however_many_buildings(self):
        """Building.estates_codes per row would be a query per building."""
        def queries():
            with CaptureQueriesContext(connection) as ctx:
                self._building_list()
            return len(ctx.captured_queries)

        self._building_list()  # settle the active team, which saves the session
        before = queries()
        for i in range(3):
            building = Building.objects.create(
                key=f"B{i}", name=f"Building {i}", campus=self.campus)
            Room.objects.create(lsd_id=f"b{i}", name="1.01", building=building,
                                building_code=f"09{i}0")
        self.assertEqual(queries(), before)

    def test_the_building_list_filters_on_a_code_listing_each_building_once(self):
        Room.objects.create(lsd_id="r4", name="G.03", building=self.hub,
                            building_code="0228")
        cl = self._building_list(estates_code='0228').context['cl']
        self.assertEqual(
            sorted(b.name for b in cl.result_list),
            ["40 George Sq Lower Hub", "Appleton Tower"])
        cl = self._building_list(estates_code='0222').context['cl']
        self.assertEqual([b.name for b in cl.result_list], ["40 George Sq Lower Hub"])

    def test_the_code_filter_offers_each_code_once(self):
        cl = self._building_list().context['cl']
        spec = next(s for s in cl.filter_specs if s.parameter_name == 'estates_code')
        self.assertEqual(spec.lookup_choices, [("0222", "0222"), ("0228", "0228")])

    def test_a_room_is_searchable_by_its_estates_code(self):
        resp = self.client.get(
            reverse('admin:estate_room_changelist'), {'q': '0222'})
        self.assertEqual(
            [r.name for r in resp.context['cl'].result_list], ["G.02"])

    def test_the_room_list_names_inactive_rooms_and_filters_on_them(self):
        url = reverse('admin:estate_room_changelist')
        self.assertContains(self.client.get(url), "Inactive", count=1)
        resp = self.client.get(url, {'active__exact': '0'})
        self.assertEqual(
            [r.name for r in resp.context['cl'].result_list], ["G.01"])
