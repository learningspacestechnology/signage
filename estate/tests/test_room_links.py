"""Linking the room_schedules display records to the estate directory.

Nothing here links automatically. Every suggestion is offered for confirmation,
which is what most of these assert.
"""

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse

from estate.models import Building, BuildingLink, Campus, Room, RoomLink
from estate.tests.helpers import grant_all_locations
from room_schedules.models import Building as DisplayBuilding
from room_schedules.models import Room as DisplayRoom
from screens.models import Team


class RoomLinksTestCase(TestCase):
    def setUp(self):
        Team.objects.all().delete()
        # ActiveTeamMiddleware serves a staff user with no team a 403 page
        # before any view runs, so every client here needs one.
        self.team = Team.objects.create(name="Alpha")
        self.campus = Campus.objects.create(name="Central")
        self.estate_building = Building.objects.create(
            key="AT", name="Appleton Tower", campus=self.campus)
        self.other_estate_building = Building.objects.create(
            key="IF", name="Informatics Forum", campus=self.campus)
        self.lt2 = Room.objects.create(
            lsd_id="r1", name="LT2", building=self.estate_building)
        self.lt3 = Room.objects.create(
            lsd_id="r2", name="LT3", building=self.estate_building)
        # In a different building, so it must never be a candidate for LT2.
        self.forum_room = Room.objects.create(
            lsd_id="r3", name="LT2", building=self.other_estate_building)

        self.display_building = DisplayBuilding.objects.create(name="Appleton Tower")
        self.display_room = DisplayRoom.objects.create(
            name="LT2", building=self.display_building)

        self.url = reverse('admin:estate_room_links')

    def _user(self, *, can_link=True, username="ops"):
        user = User.objects.create_user(username, f'{username}@x', 'pw', is_staff=True)
        grant_all_locations(user)
        user.teams.add(self.team)
        if can_link:
            user.user_permissions.add(Permission.objects.get(
                content_type=ContentType.objects.get_for_model(DisplayRoom),
                codename='change_room'))
        client = Client()
        client.force_login(user)
        return user, client

    def _link_building(self, client, estate=None):
        return client.post(self.url, {
            'action': 'link_building',
            'display_building_id': self.display_building.pk,
            'estate_building_id': (estate or self.estate_building).pk,
        }, follow=True)


class AccessTests(RoomLinksTestCase):
    def test_it_needs_permission_to_change_display_rooms(self):
        _, client = self._user(can_link=False)
        self.assertEqual(client.get(self.url).status_code, 403)

    def test_a_permitted_user_can_open_it(self):
        _, client = self._user()
        self.assertEqual(client.get(self.url).status_code, 200)

    def test_it_appears_as_a_tab_on_the_o365_pages_too(self):
        """The tab strip is a project override of the submodule's template."""
        _, client = self._user()
        client.get(self.url)  # the estate page itself
        for name in ('admin:room_schedules_o365_assigned',
                     'admin:room_schedules_o365_unassigned'):
            resp = client.get(reverse(name))
            self.assertContains(resp, self.url, msg_prefix=name)
            self.assertContains(resp, "Estate links", msg_prefix=name)


class BuildingLinkTests(RoomLinksTestCase):
    def test_a_matching_building_is_suggested_but_not_linked(self):
        _, client = self._user()
        entry = client.get(self.url).context['buildings'][0]

        self.assertIsNone(entry['link'])
        self.assertEqual(
            entry['suggestions'][0]['object'].pk, self.estate_building.pk)
        self.assertEqual(entry['suggestions'][0]['badge'], "Exact name")
        self.assertFalse(BuildingLink.objects.exists())

    def test_no_suggestion_radio_is_preselected(self):
        """A wrong suggestion must not be acceptable by reflex."""
        _, client = self._user()
        self.assertNotContains(client.get(self.url), 'type="radio" checked')

    def test_the_badge_is_a_word_not_only_a_colour(self):
        _, client = self._user()
        self.assertContains(client.get(self.url), "Exact name")

    def test_posting_creates_the_link_and_records_who_made_it(self):
        user, client = self._user()
        resp = self._link_building(client)

        link = BuildingLink.objects.get()
        self.assertEqual(link.display_building, self.display_building)
        self.assertEqual(link.estate_building, self.estate_building)
        self.assertEqual(link.linked_by, user)
        self.assertContains(resp, "Linked Appleton Tower to Appleton Tower.")

    def test_linking_again_moves_the_link_rather_than_duplicating_it(self):
        _, client = self._user()
        self._link_building(client)
        self._link_building(client, estate=self.other_estate_building)

        self.assertEqual(BuildingLink.objects.count(), 1)
        self.assertEqual(
            BuildingLink.objects.get().estate_building, self.other_estate_building)

    def test_choosing_nothing_says_so_rather_than_failing_silently(self):
        _, client = self._user()
        resp = client.post(self.url, {
            'action': 'link_building',
            'display_building_id': self.display_building.pk,
            'estate_building_id': '',
        }, follow=True)

        self.assertFalse(BuildingLink.objects.exists())
        self.assertContains(resp, "Choose a building to link")

    def test_a_radio_choice_wins_over_the_empty_full_list_select(self):
        """Both controls share a field name; the empty one must not win."""
        _, client = self._user()
        client.post(self.url, {
            'action': 'link_building',
            'display_building_id': self.display_building.pk,
            # Order as the browser sends it: radios first, then the select.
            'estate_building_id': [str(self.estate_building.pk), ''],
        }, follow=True)

        self.assertEqual(
            BuildingLink.objects.get().estate_building, self.estate_building)

    def test_unlinking_removes_it(self):
        _, client = self._user()
        self._link_building(client)
        link = BuildingLink.objects.get()

        client.post(self.url, {
            'action': 'unlink', 'link_kind': 'building', 'link_id': link.pk},
            follow=True)

        self.assertFalse(BuildingLink.objects.exists())


class RoomLinkTests(RoomLinksTestCase):
    def test_rooms_offer_nothing_until_their_building_is_linked(self):
        """Room labels only become unambiguous inside a building."""
        _, client = self._user()
        group = client.get(self.url).context['room_groups'][0]

        self.assertIsNone(group['estate_building'])
        self.assertEqual(group['candidates'], [])
        self.assertEqual(group['rooms'][0]['suggestions'], [])

    def test_the_page_says_to_link_the_building_first(self):
        _, client = self._user()
        self.assertContains(
            client.get(self.url), "Link this building above before linking its rooms")

    def test_candidates_are_restricted_to_the_linked_building(self):
        _, client = self._user()
        self._link_building(client)

        group = client.get(self.url).context['room_groups'][0]
        self.assertEqual(
            {r.pk for r in group['candidates']}, {self.lt2.pk, self.lt3.pk})
        self.assertNotIn(self.forum_room, group['candidates'])

    def test_the_same_room_name_in_another_building_is_not_suggested(self):
        _, client = self._user()
        self._link_building(client)

        entry = client.get(self.url).context['room_groups'][0]['rooms'][0]
        suggested = {s['object'].pk for s in entry['suggestions']}
        self.assertIn(self.lt2.pk, suggested)
        self.assertNotIn(self.forum_room.pk, suggested)

    def test_posting_creates_the_room_link(self):
        user, client = self._user()
        self._link_building(client)

        client.post(self.url, {
            'action': 'link_room',
            'display_room_id': self.display_room.pk,
            'estate_room_id': self.lt2.pk,
        }, follow=True)

        link = RoomLink.objects.get()
        self.assertEqual(link.estate_room, self.lt2)
        self.assertEqual(link.linked_by, user)

    def test_an_estate_room_already_linked_elsewhere_is_refused_clearly(self):
        _, client = self._user()
        self._link_building(client)
        other_display = DisplayRoom.objects.create(
            name="LT3", building=self.display_building)
        client.post(self.url, {
            'action': 'link_room', 'display_room_id': self.display_room.pk,
            'estate_room_id': self.lt2.pk}, follow=True)

        resp = client.post(self.url, {
            'action': 'link_room', 'display_room_id': other_display.pk,
            'estate_room_id': self.lt2.pk}, follow=True)

        self.assertEqual(RoomLink.objects.count(), 1)
        self.assertContains(resp, "is already linked to")

    def test_relinking_the_same_display_room_is_allowed(self):
        _, client = self._user()
        self._link_building(client)
        for room in (self.lt2, self.lt3):
            client.post(self.url, {
                'action': 'link_room', 'display_room_id': self.display_room.pk,
                'estate_room_id': room.pk}, follow=True)

        self.assertEqual(RoomLink.objects.count(), 1)
        self.assertEqual(RoomLink.objects.get().estate_room, self.lt3)

    def test_a_linked_room_no_longer_offers_suggestions(self):
        _, client = self._user()
        self._link_building(client)
        client.post(self.url, {
            'action': 'link_room', 'display_room_id': self.display_room.pk,
            'estate_room_id': self.lt2.pk}, follow=True)

        entry = client.get(self.url).context['room_groups'][0]['rooms'][0]
        self.assertIsNotNone(entry['link'])
        self.assertEqual(entry['suggestions'], [])


class SubmoduleIsolationTests(TestCase):
    """The link is owned by estate, so room_schedules gains no dependency."""

    def test_room_schedules_models_carry_no_estate_foreign_key(self):
        fields = {f.name for f in DisplayRoom._meta.get_fields()}
        self.assertNotIn('estate_room', fields)
        self.assertNotIn('estate_building',
                         {f.name for f in DisplayBuilding._meta.get_fields()})

    def test_the_reverse_accessor_is_still_available_where_it_is_useful(self):
        building = DisplayBuilding.objects.create(name="B")
        room = DisplayRoom.objects.create(name="R", building=building)
        campus = Campus.objects.create(name="C")
        estate_building = Building.objects.create(
            key="k", name="EB", campus=campus)
        estate_room = Room.objects.create(
            lsd_id="x", name="ER", building=estate_building)
        RoomLink.objects.create(display_room=room, estate_room=estate_room)

        self.assertEqual(room.estate_link.estate_room, estate_room)


class TabTemplateDriftTests(TestCase):
    """Our tab strip is a fork of the submodule's; it must not lose its tabs.

    Modelled on test_accent_picker's fork-drift test: a submodule update that
    reworks the strip should fail loudly here rather than silently dropping a
    tab from the page.
    """

    def _ours(self):
        from pathlib import Path
        from django.conf import settings
        return (Path(settings.BASE_DIR) / 'templates' / 'admin' /
                'room_schedules' / 'room' / '_o365_tabs.html').read_text()

    def test_it_still_carries_the_submodule_versions_two_tabs(self):
        ours = self._ours()
        self.assertIn("Assigned per Building", ours)
        self.assertIn("Unassigned", ours)

    def test_it_still_carries_the_submodule_versions_sync_form(self):
        self.assertIn("Sync O365 rooms now", self._ours())

    def test_it_adds_exactly_the_one_estate_tab(self):
        self.assertEqual(self._ours().count("Estate links"), 1)
