"""The screen form picks a room in two steps: a building, then a room in it."""

import re
from pathlib import Path

from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.test import Client, TestCase
from django.urls import reverse

from estate.models import Building, Campus, Room
from estate.picker import room_picker_label
from estate.tests.helpers import grant_all_locations
from estate.tests.test_estate_admin import _perms
from screens.models import Playlist, Schedule, Screen, Team


class RoomPickerTestCase(TestCase):
    def setUp(self):
        Team.objects.all().delete()
        self.team = Team.objects.create(name="Alpha")
        self.campus = Campus.objects.create(name="Central South")
        self.building = Building.objects.create(
            key="cs|1gs", name="1 George Square", campus=self.campus)
        self.other_building = Building.objects.create(
            key="cs|at", name="Appleton Tower", campus=self.campus)
        # The live data's own duplicate: two records, one building, one name.
        self.room = Room.objects.create(
            lsd_id="1gs1.1", name="1.1", building=self.building)
        self.twin = Room.objects.create(
            lsd_id="georgesq011.1", name="1.1", building=self.building)
        self.elsewhere = Room.objects.create(
            lsd_id="at2.14", name="2.14", building=self.other_building)

        playlist = Playlist.objects.create(name="p")
        playlist.teams.add(self.team)
        self.schedule = Schedule.objects.create(name="s", default_playlist=playlist)
        self.schedule.teams.add(self.team)
        self.screen = Screen.objects.create(
            name="Foyer", ip="10.0.0.1", schedule=self.schedule, room=self.room)
        self.screen.teams.add(self.team)
        self.change_url = reverse('admin:screens_screen_change', args=[self.screen.pk])

    def _client(self, *, change=True, view_room=True):
        user = User.objects.create_user('ed', 'e@x', 'pw', is_staff=True)
        grant_all_locations(user)
        user.teams.add(self.team)
        user.user_permissions.add(*_perms(
            Screen, *(('view_screen', 'change_screen') if change else ('view_screen',))))
        if view_room:
            user.user_permissions.add(*_perms(Room, 'view_room'))
        client = Client()
        client.force_login(user)
        client.get(reverse('admin:index'))  # initialise the active-team session
        return client

    def _pick(self, client, **params):
        return client.get(reverse('admin:estate_room_picker'), {
            'app_label': 'screens', 'model_name': 'screen', 'field_name': 'room',
            **params,
        })

    def _texts(self, response):
        self.assertEqual(response.status_code, 200)
        return [r['text'] for r in response.json()['results']]


class PickerViewTests(RoomPickerTestCase):

    def test_lists_only_the_chosen_buildings_rooms(self):
        resp = self._pick(self._client(), building=self.building.pk)
        self.assertEqual(sorted(self._texts(resp)),
                         ["1.1 (1gs1.1)", "1.1 (georgesq011.1)"])

    def test_the_datastore_id_tells_two_same_named_rooms_apart(self):
        resp = self._pick(self._client(), building=self.building.pk)
        ids = {r['id']: r['text'] for r in resp.json()['results']}
        self.assertEqual(ids[str(self.room.pk)], "1.1 (1gs1.1)")
        self.assertEqual(ids[str(self.twin.pk)], "1.1 (georgesq011.1)")

    def test_search_stays_inside_the_building(self):
        resp = self._pick(self._client(), building=self.other_building.pk, term="1.1")
        self.assertEqual(self._texts(resp), [])

    def test_search_by_datastore_id(self):
        resp = self._pick(self._client(), building=self.building.pk, term="georgesq")
        self.assertEqual(self._texts(resp), ["1.1 (georgesq011.1)"])

    def test_no_building_lists_nothing_rather_than_the_whole_estate(self):
        client = self._client()
        self.assertEqual(self._texts(self._pick(client)), [])
        self.assertEqual(self._texts(self._pick(client, building="x")), [])

    def test_without_estate_view_room_the_picker_is_refused_not_silently_empty(self):
        """The rollout trap: grant estate.view_room alongside screens.change_screen."""
        resp = self._pick(self._client(view_room=False), building=self.building.pk)
        self.assertEqual(resp.status_code, 403)

    def test_refuses_a_field_that_does_not_point_at_rooms(self):
        """The view filters on building_id; another model would be a 500."""
        resp = self._pick(self._client(), building=self.building.pk,
                          field_name='schedule')
        self.assertEqual(resp.status_code, 403)

    def test_a_room_named_after_its_id_is_not_labelled_twice(self):
        room = Room(lsd_id="bare01", name="bare01", building=self.building)
        self.assertEqual(room_picker_label(room), "bare01")


class ScreenFormTests(RoomPickerTestCase):

    def _post(self, client, **fields):
        return client.post(self.change_url, {
            'name': 'Foyer', 'ip': '10.0.0.1',
            'schedule': str(self.schedule.pk),
            'interspersed_playlist': '', 'interspersed_rate': '1',
            **fields,
        })

    def test_building_starts_as_the_rooms_building(self):
        form = self._client().get(self.change_url).context['adminform'].form
        self.assertEqual(form['building'].value(), self.building.pk)

    def test_the_current_room_is_labelled_like_the_picker(self):
        resp = self._client().get(self.change_url)
        self.assertContains(resp, "1.1 (1gs1.1)")

    def test_the_room_box_points_at_the_building_picker(self):
        resp = self._client().get(self.change_url)
        self.assertContains(resp, 'data-building-input="id_building"')
        self.assertContains(resp, reverse('admin:estate_room_picker'))
        self.assertContains(resp, 'estate/js/room_picker.js')

    def test_buildings_are_grouped_by_campus(self):
        resp = self._client().get(self.change_url)
        self.assertContains(resp, '<optgroup label="Central South">', html=False)

    def test_the_group_hover_fix_is_loaded(self):
        """Without it, hovering one building highlights its whole campus."""
        resp = self._client().get(self.change_url)
        self.assertContains(resp, 'estate/css/building_picker.css')

    def test_a_building_name_on_two_campuses_carries_its_campus(self):
        other = Campus.objects.create(name="BioQuarter")
        Building.objects.create(key="bq|ms", name="Medical School", campus=other)
        Building.objects.create(key="cs|ms", name="Medical School", campus=self.campus)
        resp = self._client().get(self.change_url)
        self.assertContains(resp, "Medical School (BioQuarter)")
        self.assertContains(resp, "Medical School (Central South)")
        # An unshared name stays bare.
        self.assertNotContains(resp, "Appleton Tower (Central South)")

    def test_saves_a_room_in_the_chosen_building(self):
        resp = self._post(self._client(), building=str(self.building.pk),
                          room=str(self.twin.pk))
        self.assertEqual(resp.status_code, 302)
        self.screen.refresh_from_db()
        self.assertEqual(self.screen.room, self.twin)

    def test_refuses_a_room_outside_the_chosen_building(self):
        resp = self._post(self._client(), building=str(self.building.pk),
                          room=str(self.elsewhere.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp.context['adminform'].form, 'room',
                             "2.14 is not in 1 George Square.")
        self.screen.refresh_from_db()
        self.assertEqual(self.screen.room, self.room)

    def test_clearing_the_building_clears_the_room(self):
        """The page disables Room with no building, so it is not submitted."""
        resp = self._post(self._client(), building='')
        self.assertEqual(resp.status_code, 302)
        self.screen.refresh_from_db()
        self.assertIsNone(self.screen.room)

    def test_unfolds_option_hover_rule_is_still_the_one_we_outrank(self):
        """building_picker.css un-highlights a hovered campus group by beating
        Unfold's hover rule on specificity. If an upgrade changes that rule's
        selector, re-check the override rather than trusting it still wins."""
        css = Path(finders.find('unfold/css/styles.css')).read_text()
        hover_selectors = set(re.findall(
            r'([^{}]*\.select2-results__option[^{}_-]*:hover)\{', css))
        self.assertEqual(
            {s.split('{')[-1].strip() for s in hover_selectors},
            {'.select2-container.select2-container--admin-autocomplete '
             '.select2-results__option:hover',
             '.select2-container.select2-container--admin-autocomplete '
             '.select2-results__option:where(.dark,.dark *):hover'})

    def test_a_view_only_user_can_still_open_the_screen(self):
        """`building` has no model attribute to render read-only from."""
        resp = self._client(change=False).get(self.change_url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'id_building')
        self.assertContains(resp, "1 George Square — 1.1")
