"""The permission grid on the Group and User pages.

Three kinds of test:

- The catalogue against the database and the rest of the code: every
  permission placed, nothing the sidebar or help pages ask for left out of
  reach, and every Delete box carrying what Django asks for when it cascades.
- Saving: what the form writes, and that it never drops a permission silently.
- The two jobs that prompted it, end to end — "only let them change screens",
  "schedules but not the Celery schedules".
"""

import re
from pathlib import Path
from types import SimpleNamespace

from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import Group, Permission, User
from django.db import models
from django.test import TestCase
from django.urls import reverse

import advertising.admin  # noqa: F401 — completes admin.site's registry
from advertising import permission_catalogue as catalogue
from advertising.permission_grid import permission_key
from estate.models import Building, Campus, Room
from estate.tests.helpers import grant_all_locations
from helpdocs import registry
from screens.models import Playlist, Schedule, ScheduleRule, Screen, Team


def _db_permissions():
    return {permission_key(p) for p in Permission.objects.select_related('content_type')}


def _permission(key):
    app_label, codename = key.split('.')
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def _errors(response):
    context = getattr(response, 'context', None) or {}
    adminform = context.get('adminform')
    return (adminform.form.errors if adminform else None,
            [f.formset.errors for f in context.get('inline_admin_formsets', [])])


def _keys(holder):
    return {permission_key(p) for p in holder.select_related('content_type')}


class CatalogueTests(TestCase):
    """The catalogue has to keep up with the models, or the grid lies."""

    def test_every_permission_is_offered_or_hidden(self):
        unplaced = _db_permissions() - catalogue.OFFERED - set(catalogue.HIDDEN)
        self.assertFalse(
            unplaced,
            "Place these in advertising/permission_catalogue.py — in a row's "
            f"bundle, or in HIDDEN with the reason: {sorted(unplaced)}")

    def test_every_catalogued_permission_exists(self):
        missing = (catalogue.OFFERED | set(catalogue.HIDDEN)) - _db_permissions()
        self.assertFalse(missing, f"No such permission: {sorted(missing)}")

    def test_nothing_is_both_offered_and_hidden(self):
        self.assertFalse(catalogue.OFFERED & set(catalogue.HIDDEN))

    def test_requires_names_real_boxes(self):
        for cell in catalogue.CELLS.values():
            if cell.action is None:
                continue
            for key in cell.row.requires.get(cell.action, ()):
                with self.subTest(cell=cell.key):
                    self.assertIn(key, catalogue.CELLS)

    def test_delete_boxes_cover_what_a_cascade_asks_for(self):
        """Django refuses a delete unless the user may delete every *registered*
        model it cascades to, so a Delete box must grant those too (directly,
        or through a box it requires)."""
        for key, cell in catalogue.CELLS.items():
            if cell.action != catalogue.DELETE:
                continue
            granted = catalogue.permissions_for({key})
            for perm in cell.permissions:
                app_label, codename = perm.split('.')
                if not codename.startswith('delete_'):
                    continue
                model = apps.get_model(app_label, codename[len('delete_'):])
                for cascaded in _cascades(model):
                    if cascaded not in admin.site._registry:
                        continue
                    needed = f'{cascaded._meta.app_label}.delete_{cascaded._meta.model_name}'
                    with self.subTest(box=key, cascades_to=needed):
                        self.assertIn(needed, granted)

    def test_sidebar_asks_only_for_grantable_permissions(self):
        asked = set()
        user = SimpleNamespace(
            is_authenticated=True, is_staff=True, is_superuser=False,
            # True, so an `and` in a lambda does not hide its second check.
            has_perm=lambda perm: asked.add(perm) or True)
        request = SimpleNamespace(user=user, path='/admin/')
        for group in settings.UNFOLD['SIDEBAR']['navigation']:
            for item in group['items']:
                item['permission'](request)
        self.assertTrue(asked)
        self.assertLessEqual(asked, catalogue.OFFERED)

    def test_help_pages_ask_only_for_grantable_permissions(self):
        asked = {p for page in registry.PAGES for p in page.permissions}
        asked |= {p for p in registry.AUDIENCE_PERMISSIONS.values() if p}
        for path in Path(registry.CONTENT_ROOT).rglob('*.md'):
            asked |= {f'{app}.{codename}' for app, codename
                      in re.findall(r'perms\.(\w+)\.(\w+)', path.read_text())}
        self.assertLessEqual(asked, catalogue.OFFERED)


def _cascades(model, seen=None):
    seen = set() if seen is None else seen
    for rel in model._meta.related_objects:
        if getattr(rel, 'on_delete', None) is models.CASCADE and rel.related_model not in seen:
            seen.add(rel.related_model)
            _cascades(rel.related_model, seen)
    return seen


class GridTestCase(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser('root', 'root@x', 'pw')
        self.client.force_login(self.root)

    def _group(self, *keys, name='Editors'):
        group = Group.objects.create(name=name)
        group.permissions.add(*(_permission(k) for k in keys))
        return group

    def _form(self, group):
        response = self.client.get(reverse('admin:auth_group_change', args=[group.pk]))
        self.assertEqual(response.status_code, 200)
        return response.context['adminform'].form

    def _save_group(self, group, capabilities, other=None, follow=False):
        data = {'name': group.name, 'capabilities': list(capabilities)}
        if other is not None:
            data['other_permissions'] = [p.pk for p in other]
        return self.client.post(
            reverse('admin:auth_group_change', args=[group.pk]), data, follow=follow)


class GroupFormTests(GridTestCase):

    def test_a_box_is_ticked_by_its_primary_permission(self):
        form = self._form(self._group('screens.change_playlist'))
        ticked = set(form['capabilities'].value())
        self.assertIn('playlists:change', ticked)
        # Implied, so the form shows what saving will grant.
        self.assertIn('playlists:view', ticked)
        self.assertNotIn('playlists:add', ticked)

    def test_saving_unchanged_completes_the_bundle_and_keeps_the_rest(self):
        group = self._group('screens.change_playlist', 'contenttypes.add_contenttype')
        form = self._form(group)
        self.assertEqual([permission_key(p) for p in form.fields['other_permissions'].queryset],
                         ['contenttypes.add_contenttype'])

        response = self._save_group(group, form['capabilities'].value(),
                                    other=form.fields['other_permissions'].queryset)
        self.assertEqual(response.status_code, 302)

        self.assertEqual(
            _keys(group.permissions),
            catalogue.permissions_for({'playlists:change'}) | {'contenttypes.add_contenttype'})
        # The entry permissions that Edit actually needs to change a playlist's
        # contents — the reason bundles exist.
        self.assertIn('screens.delete_playlistentry', _keys(group.permissions))

    def test_unticking_an_other_permission_removes_it(self):
        group = self._group('screens.view_source', 'contenttypes.add_contenttype')
        self._save_group(group, ['content:view'], other=[])
        self.assertEqual(_keys(group.permissions), {'screens.view_source'})

    def test_other_permissions_cannot_add_anything(self):
        group = self._group('screens.view_source')
        response = self._save_group(group, ['content:view'],
                                    other=[_permission('auth.change_permission')])
        self.assertEqual(response.status_code, 200)  # redisplayed with an error
        self.assertNotIn('auth.change_permission', _keys(group.permissions))

    def test_a_partial_bundle_without_its_primary_is_kept_as_other(self):
        group = self._group('screens.add_playlistentry')
        form = self._form(group)
        self.assertNotIn('playlists:add', form['capabilities'].value())
        self.assertEqual([permission_key(p) for p in form.fields['other_permissions'].queryset],
                         ['screens.add_playlistentry'])

    def test_unticking_a_box_keeps_what_another_box_still_needs(self):
        both = catalogue.permissions_for({'display_buildings:change', 'display_rooms:change'})
        group = self._group(*both)
        self._save_group(group, ['display_rooms:view', 'display_rooms:change'])
        held = _keys(group.permissions)
        self.assertNotIn('room_schedules.change_building', held)
        # Shared by both rows' IP address inlines.
        self.assertIn('room_schedules.change_ipaddress', held)

    def test_edit_ticks_view_and_screens_edit_ticks_the_estate(self):
        group = self._group(name='Screens')
        response = self._save_group(group, ['screens:change'], follow=True)
        held = _keys(group.permissions)
        self.assertLessEqual({'screens.view_screen', 'screens.change_screen',
                              'estate.view_room', 'estate.view_building'}, held)
        self.assertContains(response, "Also ticked")

    def test_add_page_offers_the_grid(self):
        response = self.client.post(reverse('admin:auth_group_add'),
                                    {'name': 'New', 'capabilities': ['content:view']})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(_keys(Group.objects.get(name='New').permissions),
                         {'screens.view_source'})

    def test_no_raw_permission_picker_is_left(self):
        response = self.client.get(reverse('admin:auth_group_add'))
        self.assertContains(response, 'data-permission-grid')
        self.assertNotContains(response, 'name="permissions"')
        self.assertNotIn(Permission, admin.site._registry)

    def test_the_list_summarises_each_group(self):
        self._group(*catalogue.permissions_for({'content:view', 'content:add', 'content:change',
                                                'content:delete', 'screens:view'}))
        response = self.client.get(reverse('admin:auth_group_changelist'))
        self.assertContains(response, "Content: all")
        self.assertContains(response, "Screens: view")

    def test_a_view_only_user_sees_the_grid_read_only(self):
        group = self._group('screens.change_playlist')
        viewer = _staff('viewer', 'auth.view_group')
        self.client.force_login(viewer)
        response = self.client.get(reverse('admin:auth_group_change', args=[group.pk]))
        self.assertContains(response, 'permission-grid--readonly')
        self.assertNotContains(response, 'data-permission-grid')


def _staff(username, *permission_keys, team=None):
    user = User.objects.create_user(username, f'{username}@example.com', 'pw', is_staff=True)
    team = team or Team.objects.get_or_create(name='Alpha')[0]
    user.teams.add(team)
    user.user_permissions.add(*(_permission(k) for k in permission_keys))
    return user


class ScenarioTestCase(GridTestCase):
    """A group made through the grid, and a member of it using the admin."""

    def setUp(self):
        super().setUp()
        self.team = Team.objects.create(name='Alpha')
        self.playlist = Playlist.objects.create(name='Main')
        self.playlist.teams.add(self.team)
        self.schedule = Schedule.objects.create(name='Weekdays', default_playlist=self.playlist)
        self.schedule.teams.add(self.team)

    def _member(self, *boxes):
        group = Group.objects.create(name='Role')
        self._save_group(group, boxes)
        user = _staff('member', team=self.team)
        user.groups.add(group)
        user = grant_all_locations(user)
        self.client.force_login(user)
        self.client.get(reverse('admin:index'))  # initialise the active team
        return user

    def _sidebar(self):
        response = self.client.get(reverse('admin:index'))
        # Unfold keeps every item and marks the ones the user may see.
        return {item['title'] for group in response.context['sidebar_navigation']
                for item in group['items'] if item['has_permission']}


class ScreensOnlyTests(ScenarioTestCase):
    """"Only let them change screens.\""""

    def setUp(self):
        super().setUp()
        campus = Campus.objects.create(name='Central')
        self.building = Building.objects.create(key='c|lib', name='Library', campus=campus)
        self.room = Room.objects.create(lsd_id='lib1', name='Foyer', building=self.building)
        self.screen = Screen.objects.create(name='Foyer', ip='10.0.0.1', schedule=self.schedule)
        self.screen.teams.add(self.team)
        self._member('screens:view', 'screens:change')

    def test_they_can_place_a_screen_in_a_room(self):
        picker = self.client.get(reverse('admin:estate_room_picker'), {
            'app_label': 'screens', 'model_name': 'screen', 'field_name': 'room',
            'building': self.building.pk})
        self.assertEqual(picker.status_code, 200)
        self.assertEqual([r['id'] for r in picker.json()['results']], [str(self.room.pk)])

        response = self.client.post(
            reverse('admin:screens_screen_change', args=[self.screen.pk]), {
                'name': 'Foyer', 'ip': '10.0.0.1', 'schedule': str(self.schedule.pk),
                'building': str(self.building.pk), 'room': str(self.room.pk),
                'interspersed_playlist': '', 'interspersed_rate': '1',
            })
        self.assertEqual(response.status_code, 302)
        self.screen.refresh_from_db()
        self.assertEqual(self.screen.room, self.room)

    def test_nothing_else_is_in_their_sidebar(self):
        sidebar = self._sidebar()
        self.assertIn('Screens', sidebar)
        for absent in ('Content', 'Playlists', 'Schedules', 'Periodic Tasks', 'Users', 'Groups'):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, sidebar)

    def test_they_cannot_edit_a_schedule(self):
        response = self.client.get(reverse('admin:screens_schedule_change', args=[self.schedule.pk]))
        self.assertEqual(response.status_code, 403)


class SchedulesOnlyTests(ScenarioTestCase):
    """"View and edit schedules, but not the Celery schedules.\""""

    def setUp(self):
        super().setUp()
        self._member('schedules:view', 'schedules:change')

    def test_they_can_add_a_rule_to_a_schedule(self):
        response = self.client.post(
            reverse('admin:screens_schedule_change', args=[self.schedule.pk]), {
                'name': 'Weekdays', 'description': '',
                'default_playlist': str(self.playlist.pk),
                'schedulerule_set-TOTAL_FORMS': '1',
                'schedulerule_set-INITIAL_FORMS': '0',
                'schedulerule_set-MIN_NUM_FORMS': '0',
                'schedulerule_set-MAX_NUM_FORMS': '1000',
                'schedulerule_set-0-playlist': str(self.playlist.pk),
                'schedulerule_set-0-starts': '2026-01-01',
                'schedulerule_set-0-occurrences': 'RRULE:FREQ=DAILY',
                'schedulerule_set-0-start_time': '09:00:00',
                'schedulerule_set-0-end_time': '17:00:00',
                'schedulerule_set-0-priority': '1',
            })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ScheduleRule.objects.filter(schedule=self.schedule).count(), 1)

    def test_the_celery_schedules_stay_closed(self):
        self.assertNotIn('Periodic Tasks', self._sidebar())
        for url_name in ('admin:django_celery_beat_periodictask_changelist',
                         'admin:django_celery_beat_crontabschedule_changelist'):
            with self.subTest(url_name=url_name):
                self.assertEqual(self.client.get(reverse(url_name)).status_code, 403)


class UserPageTests(GridTestCase):

    def setUp(self):
        super().setUp()
        self.team = Team.objects.create(name='Alpha')
        self.person = _staff('person', 'screens.change_ticker_text', team=self.team)
        self.url = reverse('admin:auth_user_change', args=[self.person.pk])

    def _post(self, **fields):
        data = {
            'username': self.person.username, 'email': self.person.email,
            'first_name': '', 'last_name': '',
            'is_active': 'on', 'is_staff': 'on',
            'date_joined_0': '2026-01-01', 'date_joined_1': '09:00:00',
            'last_login_0': '', 'last_login_1': '',
            'teammembership_set-TOTAL_FORMS': '0', 'teammembership_set-INITIAL_FORMS': '0',
            'location_group_memberships-TOTAL_FORMS': '0',
            'location_group_memberships-INITIAL_FORMS': '0',
            **fields,
        }
        return self.client.post(self.url, data)

    def test_direct_permissions_are_edited_through_the_grid(self):
        form = self.client.get(self.url).context['adminform'].form
        self.assertEqual(form['capabilities'].value(), ['screens:ticker_text'])

        response = self._post(capabilities=['screens:ticker_text', 'screens:ticker_settings'])
        self.assertEqual(response.status_code, 302, _errors(response))
        self.assertEqual(_keys(self.person.user_permissions),
                         {'screens.change_ticker_text', 'screens.change_ticker_settings'})

    def test_effective_access_says_where_each_tick_comes_from(self):
        group = self._group('screens.view_source', 'screens.change_playlist', name='Editors')
        self.person.groups.add(group)
        html = self.client.get(self.url).content.decode()
        grid = html[html.index('permission-grid--readonly'):]
        self.assertIn('From Editors.', grid)
        self.assertIn('From direct.', grid)
        # change_playlist without its entry permissions: shown, but as partial.
        self.assertIn('permission-grid__state--partial', grid)
        self.assertIn('missing screens.add_playlistentry', grid)

    def test_effective_access_still_shows_for_an_inactive_account(self):
        self.person.is_active = False
        self.person.save()
        html = self.client.get(self.url).content.decode()
        self.assertIn('The account is inactive', html)
        self.assertIn('From direct.', html)

    def test_only_a_superuser_can_set_superuser_status(self):
        admin_user = _staff('useradmin', 'auth.view_user', 'auth.change_user', team=self.team)
        self.client.force_login(admin_user)
        response = self.client.get(reverse('admin:auth_user_change', args=[admin_user.pk]))
        self.assertNotContains(response, 'name="is_superuser"')

        self.url = reverse('admin:auth_user_change', args=[admin_user.pk])
        self.person = admin_user
        response = self._post(is_superuser='on',
                              capabilities=['users:view', 'users:change'])
        self.assertEqual(response.status_code, 302, _errors(response))
        admin_user.refresh_from_db()
        self.assertFalse(admin_user.is_superuser)
