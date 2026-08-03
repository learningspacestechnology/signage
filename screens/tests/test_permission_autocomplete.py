"""The Group/User permission pickers use autocomplete rather than the stock
two-column selector, which means the `auth.permission` autocomplete endpoint has
to be reachable by the people who actually edit groups. Django gates that
endpoint on `PermissionAdmin.has_view_permission`, so these tests pin the
behaviour: a group editor gets results, a plain staff user gets 403.
"""

import json

from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse

from screens.models import Team, TeamMembership


class PermissionAutocompleteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = reverse('admin:autocomplete')
        # ActiveTeamMiddleware 403s any non-superuser staff account with no team,
        # so both fixtures need one before they can reach the admin at all.
        cls.team = Team.objects.create(name='Alpha')

        cls.group_editor = cls._staff('editor')
        cls.group_editor.user_permissions.add(
            Permission.objects.get(codename='change_group'),
            Permission.objects.get(codename='view_group'),
        )
        cls.plain_staff = cls._staff('plain')

    @classmethod
    def _staff(cls, username):
        user = User.objects.create_user(
            username, f'{username}@example.com', 'pw', is_staff=True
        )
        TeamMembership.objects.create(user=user, team=cls.team)
        return user

    def _autocomplete(self, term):
        return self.client.get(
            self.url,
            {
                'term': term,
                'app_label': 'auth',
                'model_name': 'group',
                'field_name': 'permissions',
            },
        )

    def test_group_editor_can_search_permissions(self):
        self.client.force_login(self.group_editor)
        response = self._autocomplete('playlist')
        self.assertEqual(response.status_code, 200)

        results = json.loads(response.content)['results']
        self.assertTrue(results, 'expected at least one playlist permission')
        self.assertTrue(
            all('playlist' in r['text'].lower() for r in results),
            f'search term was not applied: {results}',
        )

    def test_search_matches_codename_and_app_label(self):
        self.client.force_login(self.group_editor)
        for term in ('add_source', 'screens'):
            with self.subTest(term=term):
                response = self._autocomplete(term)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(json.loads(response.content)['results'])

    def test_plain_staff_user_is_denied(self):
        self.client.force_login(self.plain_staff)
        self.assertEqual(self._autocomplete('playlist').status_code, 403)

    def test_permission_changelist_is_hidden_from_the_index(self):
        """The admin exists only to back autocomplete, not as a browsable list."""
        self.client.force_login(self.group_editor)
        response = self.client.get(reverse('admin:index'))
        self.assertNotContains(response, reverse('admin:auth_permission_changelist'))

    def test_group_form_uses_the_autocomplete_widget(self):
        """Guard against the stock filter_horizontal selector creeping back."""
        superuser = User.objects.create_superuser('root', 'root@example.com', 'pw')
        self.client.force_login(superuser)
        group = Group.objects.create(name='Content Editor')

        response = self.client.get(
            reverse('admin:auth_group_change', args=[group.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'admin-autocomplete')
        self.assertNotContains(response, 'selector-chooseall')
