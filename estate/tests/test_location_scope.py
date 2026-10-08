"""Location groups: a user sees only the places their groups grant.

The estate here, used throughout:

    Central                          King's Buildings
      Appleton Tower: LT2, LT3         JCMB: 1501
      Informatics Forum: G.07

One screen in each room, plus one with no room, all owned by team Alpha.
"""

from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse

from estate.location_scope import (ALL_LOCATIONS, ALL_LOCATIONS_GROUP_NAME,
                                   rooms_granted_by, scope_to_locations,
                                   visible_room_ids)
from estate.models import (Building, BuildingLink, Campus, LocationGroup,
                           LocationGroupMembership, Room)
from estate.sync import reconcile_estate
from estate.tests.helpers import grant_all_locations
from estate.tests.test_estate_sync import room_row
from screens.models import Playlist, Schedule, Screen, Team


def _perms(*models):
    return Permission.objects.filter(content_type__in=[
        ContentType.objects.get_for_model(m) for m in models])


class _Request:
    """Just enough request for the scope helpers, which read only ``user``."""

    def __init__(self, user):
        self.user = user


class LocationTestCase(TestCase):
    def setUp(self):
        Team.objects.all().delete()
        self.team = Team.objects.create(name="Alpha")

        self.central = Campus.objects.create(name="Central")
        self.kb = Campus.objects.create(name="King's Buildings")
        self.at = Building.objects.create(key="c|at", name="Appleton Tower",
                                          campus=self.central)
        self.forum = Building.objects.create(key="c|if", name="Informatics Forum",
                                             campus=self.central)
        self.jcmb = Building.objects.create(key="kb|jcmb", name="JCMB",
                                            campus=self.kb)
        self.lt2 = Room.objects.create(lsd_id="at-lt2", name="LT2",
                                       building=self.at, building_code="0131")
        self.lt3 = Room.objects.create(lsd_id="at-lt3", name="LT3",
                                       building=self.at, building_code="0131")
        self.g07 = Room.objects.create(lsd_id="if-g07", name="G.07",
                                       building=self.forum, building_code="0290")
        self.r1501 = Room.objects.create(lsd_id="jcmb-1501", name="1501",
                                         building=self.jcmb, building_code="0500")

        playlist = Playlist.objects.create(name="p")
        playlist.teams.add(self.team)
        self.schedule = Schedule.objects.create(name="s", default_playlist=playlist)
        self.schedule.teams.add(self.team)
        self.screens = {
            room.lsd_id: self._screen(f"screen-{room.lsd_id}", f"10.0.0.{i}", room)
            for i, room in enumerate([self.lt2, self.lt3, self.g07, self.r1501], 1)
        }
        self.roomless = self._screen("screen-nowhere", "10.0.0.99", None)

        self.rita = self._staff("rita")
        self.super = User.objects.create_superuser('root', 'r@x', 'pw')

    def _screen(self, name, ip, room, building=None):
        screen = Screen.objects.create(
            name=name, ip=ip, schedule=self.schedule, room=room,
            building=building)
        screen.teams.add(self.team)
        return screen

    def _staff(self, username):
        """A screen editor and estate viewer in team Alpha, with no locations."""
        user = User.objects.create_user(username, f'{username}@x', 'pw', is_staff=True)
        user.teams.add(self.team)
        user.user_permissions.add(*_perms(Screen, Campus, Building, Room))
        return user

    def _group(self, name, *, members=(), campuses=(), buildings=(), rooms=()):
        group = LocationGroup.objects.create(name=name)
        group.campuses.add(*campuses)
        group.buildings.add(*buildings)
        group.rooms.add(*rooms)
        for user in members:
            LocationGroupMembership.objects.create(user=user, group=group)
        return group

    def _visible(self, model, user=None):
        return set(scope_to_locations(model.objects.all(), _Request(user or self.rita)))

    def _client(self, user=None):
        client = Client()
        client.force_login(user or self.rita)
        client.get(reverse('admin:index'))  # settle the active team
        return client


class ResolutionTests(LocationTestCase):
    """What a user's location groups add up to."""

    def test_no_group_sees_nothing(self):
        self.assertEqual(self._visible(Room), set())
        self.assertEqual(self._visible(Building), set())
        self.assertEqual(self._visible(Campus), set())
        self.assertEqual(self._visible(Screen), set())

    def test_a_room_grant_reveals_its_building_and_campus_and_nothing_else(self):
        self._group("LT2 only", members=[self.rita], rooms=[self.lt2])
        self.assertEqual(self._visible(Room), {self.lt2})
        self.assertEqual(self._visible(Building), {self.at})
        self.assertEqual(self._visible(Campus), {self.central})
        self.assertEqual(self._visible(Screen), {self.screens["at-lt2"]})

    def test_a_building_grant_covers_every_room_in_it(self):
        self._group("AT", members=[self.rita], buildings=[self.at])
        self.assertEqual(self._visible(Room), {self.lt2, self.lt3})

    def test_a_building_grant_covers_a_room_added_later(self):
        self._group("AT", members=[self.rita], buildings=[self.at])
        new = Room.objects.create(lsd_id="at-new", name="New", building=self.at)
        self.assertIn(new, self._visible(Room))

    def test_a_campus_grant_covers_its_buildings_and_rooms(self):
        self._group("Central", members=[self.rita], campuses=[self.central])
        self.assertEqual(self._visible(Room), {self.lt2, self.lt3, self.g07})
        self.assertEqual(self._visible(Building), {self.at, self.forum})

    def test_several_groups_add_up(self):
        self._group("LT2", members=[self.rita], rooms=[self.lt2])
        self._group("JCMB", members=[self.rita], buildings=[self.jcmb])
        self.assertEqual(self._visible(Room), {self.lt2, self.r1501})
        self.assertEqual(self._visible(Campus), {self.central, self.kb})

    def test_a_room_granted_twice_over_is_counted_once(self):
        self._group("both", members=[self.rita], rooms=[self.lt2],
                    buildings=[self.at], campuses=[self.central])
        rooms = scope_to_locations(Room.objects.all(), _Request(self.rita))
        self.assertEqual(rooms.count(), 3)

    def test_another_members_group_grants_nothing(self):
        self._group("someone else's", members=[self._staff("sam")],
                    campuses=[self.central])
        self.assertEqual(self._visible(Room), set())

    def test_a_screen_with_no_room_is_hidden_from_a_restricted_user(self):
        self._group("Central", members=[self.rita], campuses=[self.central])
        self.assertNotIn(self.roomless, self._visible(Screen))

    def test_a_building_grant_covers_a_screen_in_it_with_no_room(self):
        foyer = self._screen("at-foyer", "10.0.1.1", None, building=self.at)
        self._group("AT", members=[self.rita], buildings=[self.at])
        self.assertIn(foyer, self._visible(Screen))

    def test_a_campus_grant_covers_one_too(self):
        foyer = self._screen("at-foyer", "10.0.1.1", None, building=self.at)
        self._group("Central", members=[self.rita], campuses=[self.central])
        self.assertIn(foyer, self._visible(Screen))

    def test_a_room_grant_in_the_building_does_not(self):
        """LT2 is not the foyer, though both are in Appleton Tower."""
        foyer = self._screen("at-foyer", "10.0.1.1", None, building=self.at)
        self._group("LT2 only", members=[self.rita], rooms=[self.lt2])
        self.assertNotIn(foyer, self._visible(Screen))
        self.assertIn(self.at, self._visible(Building))

    def test_a_screen_with_a_room_answers_to_the_room_not_the_building(self):
        """A building column gone stale must not widen access."""
        screen = self.screens["jcmb-1501"]
        Screen.objects.filter(pk=screen.pk).update(building=self.at)
        self._group("AT", members=[self.rita], buildings=[self.at])
        self.assertNotIn(screen, self._visible(Screen))

    def test_a_superuser_sees_everything(self):
        self.assertIs(visible_room_ids(_Request(self.super)), ALL_LOCATIONS)
        self.assertIn(self.roomless, self._visible(Screen, self.super))

    def test_the_permission_granted_directly_sees_everything(self):
        self.rita.user_permissions.add(Permission.objects.get(
            codename='access_all_locations'))
        rita = User.objects.get(pk=self.rita.pk)
        self.assertEqual(self._visible(Room, rita), set(Room.objects.all()))

    def test_the_permission_through_a_group_sees_everything(self):
        rita = grant_all_locations(self.rita)
        self.assertEqual(self._visible(Room, rita), set(Room.objects.all()))
        self.assertIn(self.roomless, self._visible(Screen, rita))

    def test_an_unrelated_model_is_refused_rather_than_passed_through(self):
        with self.assertRaises(TypeError):
            scope_to_locations(Playlist.objects.all(), _Request(self.rita))

    def test_rooms_granted_by_matches_what_a_member_sees(self):
        group = self._group("mix", members=[self.rita], rooms=[self.g07],
                            buildings=[self.jcmb])
        self.assertEqual(set(rooms_granted_by([group.pk])), self._visible(Room))


class EstateAdminTests(LocationTestCase):
    """The estate directory shows only the user's places."""

    def setUp(self):
        super().setUp()
        self._group("LT2", members=[self.rita], rooms=[self.lt2])

    def _rows(self, url, user=None):
        resp = self._client(user).get(url)
        self.assertEqual(resp.status_code, 200)
        return list(resp.context['cl'].result_list)

    def test_the_campus_list_shows_only_the_rooms_campus(self):
        rows = self._rows(reverse('admin:estate_campus_changelist'))
        self.assertEqual(rows, [self.central])

    def test_campus_counts_cover_only_visible_places(self):
        [central] = self._rows(reverse('admin:estate_campus_changelist'))
        self.assertEqual((central.n_buildings, central.n_rooms), (1, 1))

    def test_campus_counts_are_whole_for_an_unrestricted_user(self):
        rows = self._rows(reverse('admin:estate_campus_changelist'), self.super)
        central = next(c for c in rows if c == self.central)
        self.assertEqual((central.n_buildings, central.n_rooms), (2, 3))

    def test_the_building_list_shows_only_the_rooms_building(self):
        [at] = self._rows(reverse('admin:estate_building_changelist'))
        self.assertEqual(at, self.at)
        self.assertEqual((at.n_rooms, at.n_screens), (1, 1))

    def test_the_room_list_shows_only_the_granted_room(self):
        rows = self._rows(reverse('admin:estate_room_changelist'))
        self.assertEqual(rows, [self.lt2])

    def test_a_room_outside_the_grant_cannot_be_opened(self):
        resp = self._client().get(
            reverse('admin:estate_room_change', args=[self.lt3.pk]))
        # The admin's answer for an object not in get_queryset: back to the
        # index with a "doesn't exist" message, never the page.
        self.assertEqual(resp.status_code, 302)

    def test_the_estates_code_filter_offers_only_visible_codes(self):
        resp = self._client().get(reverse('admin:estate_building_changelist'))
        self.assertContains(resp, "0131")
        self.assertNotContains(resp, "0290")
        self.assertNotContains(resp, "0500")

    def test_the_link_admins_are_hidden(self):
        user = self._staff("linker")
        user.user_permissions.add(*_perms(BuildingLink))
        self._group("LT2 too", members=[user], rooms=[self.lt2])
        resp = self._client(user).get(reverse('admin:estate_buildinglink_changelist'))
        self.assertEqual(resp.status_code, 403)

    def test_the_sync_button_is_hidden_and_the_route_refused(self):
        client = self._client()
        resp = client.get(reverse('admin:estate_room_changelist'))
        self.assertNotContains(resp, "Sync estate now")
        resp = client.post(reverse('admin:estate_sync_now'))
        self.assertEqual(resp.status_code, 403)

    def test_the_room_links_page_is_refused(self):
        from room_schedules.models import Room as DisplayRoom

        self.rita.user_permissions.add(*Permission.objects.filter(
            content_type=ContentType.objects.get_for_model(DisplayRoom),
            codename='change_room'))
        resp = self._client().get(reverse('admin:estate_room_links'))
        self.assertEqual(resp.status_code, 403)


class ScreenAdminTests(LocationTestCase):
    """Screens, and the screen form's pickers."""

    def setUp(self):
        super().setUp()
        self._group("AT", members=[self.rita], buildings=[self.at])
        self.lt2_screen = self.screens["at-lt2"]
        self.change_url = reverse('admin:screens_screen_change',
                                  args=[self.lt2_screen.pk])

    def _post(self, client, **fields):
        return client.post(self.change_url, {
            'name': self.lt2_screen.name, 'ip': self.lt2_screen.ip,
            'schedule': str(self.schedule.pk),
            'interspersed_playlist': '', 'interspersed_rate': '1',
            # Both users here hold the ticker permissions, so the form has them.
            'ticker_layout': 'OVERLAY', 'ticker_style_preset': 'CLASSIC',
            **fields,
        })

    def test_the_screen_list_is_team_and_location_scoped(self):
        resp = self._client().get(reverse('admin:screens_screen_changelist'))
        self.assertEqual(set(resp.context['cl'].result_list),
                         {self.screens["at-lt2"], self.screens["at-lt3"]})

    def test_the_no_room_filter_option_is_not_offered(self):
        resp = self._client().get(reverse('admin:screens_screen_changelist'))
        self.assertNotContains(resp, "No location set")

    def test_the_building_box_offers_only_visible_buildings(self):
        resp = self._client().get(self.change_url)
        field = resp.context['adminform'].form.fields['building']
        self.assertEqual(set(field.queryset), {self.at})

    def test_the_building_box_is_not_narrowed_for_the_next_user(self):
        """The declared field is shared; scoping it in place would leak."""
        self._client().get(self.change_url)
        resp = self._client(self.super).get(self.change_url)
        field = resp.context['adminform'].form.fields['building']
        self.assertEqual(set(field.queryset), set(Building.objects.all()))

    def test_the_room_picker_lists_only_visible_rooms(self):
        self._group("LT2 only", members=[self._staff("una")], rooms=[self.lt2])
        una = User.objects.get(username="una")
        resp = self._client(una).get(reverse('admin:estate_room_picker'), {
            'app_label': 'screens', 'model_name': 'screen', 'field_name': 'room',
            'building': self.at.pk})
        self.assertEqual([r['id'] for r in resp.json()['results']],
                         [str(self.lt2.pk)])

    def test_a_room_in_scope_saves(self):
        resp = self._post(self._client(), building=str(self.at.pk),
                          room=str(self.lt3.pk))
        self.assertEqual(resp.status_code, 302)
        self.lt2_screen.refresh_from_db()
        self.assertEqual(self.lt2_screen.room, self.lt3)

    def test_a_crafted_post_cannot_place_a_screen_outside_the_users_rooms(self):
        resp = self._post(self._client(), building=str(self.jcmb.pk),
                          room=str(self.r1501.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('room', resp.context['adminform'].form.errors)
        self.lt2_screen.refresh_from_db()
        self.assertEqual(self.lt2_screen.room, self.lt2)

    def test_a_restricted_user_must_set_a_building(self):
        resp = self._post(self._client(), building='', room='')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('building', resp.context['adminform'].form.errors)

    def test_a_building_granted_whole_may_hold_a_screen_with_no_room(self):
        resp = self._post(self._client(), building=str(self.at.pk), room='')
        self.assertEqual(resp.status_code, 302)
        self.lt2_screen.refresh_from_db()
        self.assertIsNone(self.lt2_screen.room)
        self.assertEqual(self.lt2_screen.building, self.at)

    def test_a_building_seen_through_one_room_needs_a_room(self):
        """The Building box offers it, but the screen would vanish on save."""
        una = self._staff("una")
        self._group("LT2 only", members=[una], rooms=[self.lt2])
        resp = self._post(self._client(una), building=str(self.at.pk), room='')
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(
            resp.context['adminform'].form, 'room',
            "Choose a room. Your locations include rooms in Appleton Tower but "
            "not the whole building, so a screen with no room there would "
            "disappear from your list.")
        self.lt2_screen.refresh_from_db()
        self.assertEqual(self.lt2_screen.room, self.lt2)

    def test_the_rule_is_not_left_on_the_form_for_the_next_user(self):
        self._client().get(self.change_url)
        resp = self._client(self.super).get(self.change_url)
        form = resp.context['adminform'].form
        self.assertIsNone(form.wholly_visible_buildings)
        self.assertFalse(form.fields['building'].required)

    def test_an_unrestricted_user_may_still_leave_the_room_blank(self):
        # A superuser across all teams must name one; see TeamScopedAdminMixin.
        resp = self._post(self._client(self.super), building='', room='',
                          teams=[str(self.team.pk)])
        self.assertEqual(resp.status_code, 302)
        self.lt2_screen.refresh_from_db()
        self.assertIsNone(self.lt2_screen.room)
        self.assertIsNone(self.lt2_screen.building)


class BuildingPageTests(LocationTestCase):
    def setUp(self):
        super().setUp()
        self._group("LT2", members=[self.rita], rooms=[self.lt2])

    def test_a_building_outside_the_users_places_is_404(self):
        resp = self._client().get(
            reverse('admin:estate_building_screens', args=[self.jcmb.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_the_permission_check_still_comes_first(self):
        user = User.objects.create_user('vic', 'v@x', 'pw', is_staff=True)
        user.teams.add(self.team)
        resp = self._client(user).get(
            reverse('admin:estate_building_screens', args=[self.jcmb.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_dark_rooms_are_limited_to_the_users_rooms(self):
        self.screens["at-lt2"].delete()
        resp = self._client().get(
            reverse('admin:estate_building_screens', args=[self.at.pk]))
        self.assertEqual(list(resp.context['dark_rooms']), [self.lt2])


class DashboardTests(LocationTestCase):
    def test_the_rollup_covers_only_the_users_buildings(self):
        self._group("AT", members=[self.rita], buildings=[self.at])
        resp = self._client().get(reverse('admin:index'))
        self.assertEqual([b['name'] for b in resp.context['screens_by_building']],
                         ["Appleton Tower"])
        self.assertEqual(resp.context['screens_total'], 2)

    def test_the_footnote_says_so(self):
        self._group("AT", members=[self.rita], buildings=[self.at])
        resp = self._client().get(reverse('admin:index'))
        self.assertContains(resp, "Counts cover screens in your teams and locations.")

    def test_no_locations_gets_a_notice_not_an_error(self):
        resp = self._client().get(reverse('admin:index'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "You do not have access to any locations")

    def test_an_unrestricted_user_gets_neither(self):
        resp = self._client(grant_all_locations(self.rita)).get(reverse('admin:index'))
        self.assertContains(resp, "Counts cover screens in your teams.")
        self.assertNotContains(resp, "You do not have access to any locations")

    def test_a_superuser_is_told_about_stale_grants(self):
        self._group("AT", buildings=[self.at])
        Building.objects.filter(pk=self.at.pk).update(missing_from_source=True)
        resp = self._client(self.super).get(reverse('admin:index'))
        self.assertContains(resp, "1 location group grants a place")
        self.assertContains(resp, "?needs_review=1")


class LocationGroupAdminTests(LocationTestCase):
    def setUp(self):
        super().setUp()
        self.add_url = reverse('admin:estate_locationgroup_add')

    def _form(self, **fields):
        return {
            'name': 'Group', 'description': '',
            'memberships-TOTAL_FORMS': '0', 'memberships-INITIAL_FORMS': '0',
            'memberships-MIN_NUM_FORMS': '0', 'memberships-MAX_NUM_FORMS': '1000',
            **fields,
        }

    def test_it_is_superuser_only(self):
        rita = grant_all_locations(self.rita)
        rita.user_permissions.add(*_perms(LocationGroup))
        client = self._client(rita)
        resp = client.get(reverse('admin:estate_locationgroup_changelist'))
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(client.post(self.add_url, self._form()).status_code, 403)

    def test_it_saves_grants_and_members(self):
        resp = self._client(self.super).post(self.add_url, self._form(
            campuses=[str(self.kb.pk)], buildings=[str(self.at.pk)],
            rooms=[str(self.g07.pk)],
            **{'memberships-TOTAL_FORMS': '1', 'memberships-0-user': str(self.rita.pk)}))
        self.assertEqual(resp.status_code, 302)
        group = LocationGroup.objects.get(name='Group')
        self.assertEqual(list(group.members.all()), [self.rita])
        self.assertEqual(self._visible(Room),
                         {self.lt2, self.lt3, self.g07, self.r1501})

    def test_the_shortcut_adds_the_buildings_current_rooms(self):
        resp = self._client(self.super).post(self.add_url, self._form(
            add_rooms_from=[str(self.at.pk)]), follow=True)
        group = LocationGroup.objects.get(name='Group')
        self.assertEqual(set(group.rooms.all()), {self.lt2, self.lt3})
        self.assertFalse(group.buildings.exists())
        self.assertContains(resp, "Added 2 rooms from Appleton Tower.")

    def test_the_shortcut_survives_rooms_chosen_alongside_it(self):
        """save_m2m does rooms.set(); the shortcut must run after it."""
        self._client(self.super).post(self.add_url, self._form(
            rooms=[str(self.g07.pk)], add_rooms_from=[str(self.at.pk)]))
        group = LocationGroup.objects.get(name='Group')
        self.assertEqual(set(group.rooms.all()), {self.lt2, self.lt3, self.g07})

    def test_the_shortcut_is_a_snapshot(self):
        self._client(self.super).post(self.add_url, self._form(
            add_rooms_from=[str(self.at.pk)]))
        new = Room.objects.create(lsd_id="at-new", name="New", building=self.at)
        group = LocationGroup.objects.get(name='Group')
        self.assertNotIn(new, set(rooms_granted_by([group.pk])))

    def test_a_grant_missing_from_the_datastore_is_flagged(self):
        group = self._group("AT", buildings=[self.at])
        self._group("fine", rooms=[self.g07])
        Building.objects.filter(pk=self.at.pk).update(missing_from_source=True)
        client = self._client(self.super)

        resp = client.get(reverse('admin:estate_locationgroup_changelist')
                          + '?needs_review=1')
        self.assertEqual(list(resp.context['cl'].result_list), [group])

        resp = client.get(reverse('admin:estate_locationgroup_change',
                                  args=[group.pk]))
        self.assertContains(resp, "Appleton Tower (missing from datastore)")
        self.assertContains(resp, "Building: Appleton Tower (Central)")

    def test_the_list_summarises_each_group(self):
        self._group("mix", members=[self.rita], campuses=[self.kb],
                    buildings=[self.at], rooms=[self.lt2, self.g07])
        resp = self._client(self.super).get(
            reverse('admin:estate_locationgroup_changelist'))
        self.assertContains(resp, "1 campus, 1 building, 2 rooms")
        [row] = resp.context['cl'].result_list
        self.assertEqual(row.n_members, 1)


class UserAdminTests(LocationTestCase):
    def test_the_users_list_says_where_each_user_can_see(self):
        self._group("AT people", members=[self.rita], buildings=[self.at])
        grant_all_locations(self._staff("alf"))
        self._staff("nell")
        resp = self._client(self.super).get(reverse('admin:auth_user_changelist'))
        rows = {u.username: u for u in resp.context['cl'].result_list}
        admin_ = resp.context['cl'].model_admin
        self.assertEqual(admin_.show_locations(rows['rita']), "AT people")
        self.assertEqual(admin_.show_locations(rows['alf']), "All locations")
        self.assertEqual(admin_.show_locations(rows['root']), "All locations")
        self.assertEqual(admin_.show_locations(rows['nell']), "No access")

    def test_the_filter_finds_users_with_no_location_access(self):
        self._group("AT people", members=[self.rita], buildings=[self.at])
        grant_all_locations(self._staff("alf"))
        self._staff("nell")
        client = self._client(self.super)
        url = reverse('admin:auth_user_changelist')
        by = {value: {u.username for u in
                      client.get(url, {'location_access': value})
                      .context['cl'].result_list}
              for value in ('all', 'some', 'none')}
        self.assertEqual(by['all'], {'alf', 'root'})
        self.assertEqual(by['some'], {'rita'})
        self.assertEqual(by['none'], {'nell'})

    def test_the_add_form_grants_location_groups(self):
        group = self._group("AT people", buildings=[self.at])
        self._client(self.super).post(reverse('admin:auth_user_add'), {
            'email': 'new@x.ac.uk', 'first_name': '', 'last_name': '',
            'is_staff': 'on', 'location_groups': [str(group.pk)],
            'password1': '', 'password2': '',
        })
        user = User.objects.get(username='new@x.ac.uk')
        self.assertEqual(list(user.location_groups.all()), [group])

    def test_the_change_page_has_a_location_group_inline_for_superusers(self):
        url = reverse('admin:auth_user_change', args=[self.rita.pk])
        resp = self._client(self.super).get(url)
        self.assertContains(resp, 'location_group_memberships-TOTAL_FORMS')


class SyncTests(TestCase):
    """A granted place the datastore drops is flagged, never deleted."""

    def setUp(self):
        reconcile_estate([
            room_row("r1"),
            room_row("r2"),
            room_row("r3", campus="King's Buildings", building="JCMB"),
        ])

    def test_a_granted_room_is_flagged_not_deleted(self):
        group = LocationGroup.objects.create(name="g")
        group.rooms.add(Room.objects.get(lsd_id="r2"))
        reconcile_estate([room_row("r1"), room_row("r3", campus="King's Buildings",
                                                   building="JCMB")])
        room = Room.objects.get(lsd_id="r2")
        self.assertTrue(room.missing_from_source)
        self.assertEqual(list(group.rooms.all()), [room])

    def test_a_granted_building_and_campus_are_flagged_not_deleted(self):
        group = LocationGroup.objects.create(name="g")
        group.buildings.add(Building.objects.get(name="JCMB"))
        group.campuses.add(Campus.objects.get(name="King's Buildings"))
        reconcile_estate([room_row("r1"), room_row("r2")])
        self.assertTrue(Building.objects.get(name="JCMB").missing_from_source)
        self.assertTrue(
            Campus.objects.get(name="King's Buildings").missing_from_source)

    def test_a_room_granted_alongside_a_stale_one_is_not_flagged(self):
        group = LocationGroup.objects.create(name="g")
        group.rooms.add(*Room.objects.filter(lsd_id__in=["r1", "r2"]))
        reconcile_estate([room_row("r1"), room_row("r3", campus="King's Buildings",
                                                   building="JCMB")])
        self.assertFalse(Room.objects.get(lsd_id="r1").missing_from_source)

    def test_a_building_grant_covers_a_room_a_later_run_adds(self):
        group = LocationGroup.objects.create(name="g")
        group.buildings.add(Building.objects.get(name="Appleton Tower"))
        reconcile_estate([room_row("r1"), room_row("r2"), room_row("r4"),
                          room_row("r3", campus="King's Buildings", building="JCMB")])
        self.assertIn(Room.objects.get(lsd_id="r4"),
                      set(rooms_granted_by([group.pk])))


class MigrationTests(TestCase):
    """0005 keeps every existing staff user seeing every location."""

    def _forwards(self):
        import_module('estate.migrations.0005_all_locations_group').forwards(apps, None)

    def test_existing_staff_join_the_all_locations_group(self):
        active = User.objects.create_user('a', 'a@x', 'pw', is_staff=True)
        inactive = User.objects.create_user('b', 'b@x', 'pw', is_staff=True,
                                            is_active=False)
        public = User.objects.create_user('c', 'c@x', 'pw')
        self._forwards()
        group = Group.objects.get(name=ALL_LOCATIONS_GROUP_NAME)
        self.assertEqual(set(group.user_set.all()), {active, inactive})
        self.assertNotIn(public, group.user_set.all())
        self.assertTrue(User.objects.get(pk=active.pk)
                        .has_perm('estate.access_all_locations'))

    def test_it_can_run_twice(self):
        User.objects.create_user('a', 'a@x', 'pw', is_staff=True)
        self._forwards()
        self._forwards()
        group = Group.objects.get(name=ALL_LOCATIONS_GROUP_NAME)
        self.assertEqual(group.permissions.count(), 1)
        self.assertEqual(group.user_set.count(), 1)
