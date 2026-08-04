"""Tests for the in-app help documentation.

Follows the project's existing conventions: plain Django `TestCase` with
`Client`, permissions granted explicitly (see `screens/tests/test_team_scoping.py`),
and custom admin pages exercised through the URL they are actually served at
(see `room_schedules/tests/test_o365_sync.py`).
"""
from django.contrib.auth.models import Permission, User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from screens.models import Team, TeamMembership

from helpdocs import registry, rendering


def _staff_user(username, team=True, superuser=False):
    if superuser:
        user = User.objects.create_superuser(username, f'{username}@demo.invalid', 'pw')
    else:
        user = User.objects.create_user(
            username, f'{username}@demo.invalid', 'pw', is_staff=True,
        )
    if team:
        team_obj, _ = Team.objects.get_or_create(name='Test Team')
        TeamMembership.objects.create(user=user, team=team_obj)
    return user


def _client_for(user):
    client = Client()
    client.force_login(user)
    return client


def _grant(user, *specs):
    """Grant 'app_label.codename' permissions and return a fresh instance.

    Django caches permissions on the user object, so callers must use the value
    returned here rather than the one they passed in.
    """
    for spec in specs:
        app_label, codename = spec.split('.')
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label=app_label, codename=codename,
            )
        )
    return User.objects.get(pk=user.pk)


def _grant_app(user, app_label):
    for permission in Permission.objects.filter(
        content_type__app_label=app_label
    ):
        user.user_permissions.add(permission)
    return User.objects.get(pk=user.pk)


class HelpIndexTests(TestCase):
    def setUp(self):
        self.user = _staff_user('reader')

    def test_index_renders_for_plain_staff_user(self):
        response = _client_for(self.user).get(reverse('admin:help_index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Search these pages')

    def test_index_lists_the_pages_the_reader_can_open(self):
        user = _grant_app(self.user, 'screens')
        response = _client_for(user).get(reverse('admin:help_index'))
        for page in registry.pages_for(registry.USERS):
            with self.subTest(slug=page.slug):
                self.assertContains(response, page.url)

    def test_index_hides_pages_the_reader_lacks_permission_for(self):
        """A reader with no model permissions sees only the ungated pages."""
        response = _client_for(self.user).get(reverse('admin:help_index'))
        for page in registry.PAGES:
            if page.audience != registry.USERS:
                continue
            with self.subTest(slug=page.slug):
                if page.permissions:
                    self.assertNotContains(response, page.url)
                else:
                    self.assertContains(response, page.url)

    def test_empty_sections_disappear(self):
        """'Content' holds only gated pages, so its heading must go too."""
        response = _client_for(self.user).get(reverse('admin:help_index'))
        self.assertNotContains(response, '>Content</h2>')

        user = _grant(self.user, 'screens.view_source')
        response = _client_for(user).get(reverse('admin:help_index'))
        self.assertContains(response, '>Content</h2>')

    def test_anonymous_is_redirected_to_login(self):
        response = Client().get(reverse('admin:help_index'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_unknown_audience_is_404(self):
        response = _client_for(self.user).get('/admin/help/nonsense/')
        self.assertEqual(response.status_code, 404)


class HelpPageTests(TestCase):
    def setUp(self):
        self.user = _staff_user('reader')

    def test_every_user_page_renders(self):
        user = _grant_app(self.user, 'screens')
        client = _client_for(user)
        for page in registry.pages_for(registry.USERS):
            with self.subTest(slug=page.slug):
                response = client.get(page.url)
                self.assertEqual(response.status_code, 200)

    def test_every_page_renders_without_raising(self):
        """Covers technical pages too, which the view would gate."""
        for page in registry.PAGES:
            with self.subTest(slug=f'{page.audience}/{page.slug}'):
                rendered = rendering.render_page(page)
                self.assertIsNotNone(rendered)
                self.assertTrue(rendered['title'])
                self.assertTrue(rendered['html'])

    def test_unknown_slug_is_404(self):
        response = _client_for(self.user).get('/admin/help/users/no-such-page/')
        self.assertEqual(response.status_code, 404)


class TechnicalDocsPermissionTests(TestCase):
    """The technical set is gated in the view, not merely hidden in the nav."""

    def setUp(self):
        self.user = _staff_user('technician')
        self.page = registry.pages_for(registry.TECHNICAL)[0]

    def _grant(self):
        self.user.user_permissions.add(
            Permission.objects.get(codename='view_technical_docs')
        )
        # Permissions are cached on the instance for the life of a request.
        self.user = User.objects.get(pk=self.user.pk)

    def test_section_forbidden_without_permission(self):
        response = _client_for(self.user).get(
            reverse('admin:help_section', kwargs={'audience': 'technical'})
        )
        self.assertEqual(response.status_code, 403)

    def test_page_forbidden_without_permission(self):
        response = _client_for(self.user).get(self.page.url)
        self.assertEqual(response.status_code, 403)

    def test_allowed_with_permission(self):
        self._grant()
        client = _client_for(self.user)
        self.assertEqual(client.get(self.page.url).status_code, 200)
        self.assertEqual(
            client.get(
                reverse('admin:help_section', kwargs={'audience': 'technical'})
            ).status_code,
            200,
        )

    def test_superuser_has_it_implicitly(self):
        superuser = _staff_user('boss', superuser=True)
        self.assertEqual(_client_for(superuser).get(self.page.url).status_code, 200)

    def test_sidebar_entry_follows_the_permission(self):
        technical_url = reverse(
            'admin:help_section', kwargs={'audience': 'technical'}
        )
        response = _client_for(self.user).get(reverse('admin:index'))
        self.assertNotContains(response, technical_url)

        self._grant()
        response = _client_for(self.user).get(reverse('admin:index'))
        self.assertContains(response, technical_url)


class TeamlessUserTests(TestCase):
    """Help requires full access — a teamless user gets the same 403 page here
    as everywhere else in the admin. Pinned so a later middleware change can't
    silently open it up."""

    def setUp(self):
        self.user = _staff_user('newcomer', team=False)

    def test_help_index_is_blocked(self):
        response = _client_for(self.user).get(reverse('admin:help_index'))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'No team assigned', status_code=403)

    def test_help_page_is_blocked(self):
        page = registry.pages_for(registry.USERS)[0]
        self.assertEqual(_client_for(self.user).get(page.url).status_code, 403)


class PagePermissionTests(TestCase):
    """Per-page permissions, layered on top of the audience gate."""

    def setUp(self):
        self.user = _staff_user('limited')
        self.page = registry.get_page(registry.USERS, 'content')

    def test_page_is_forbidden_without_the_permission(self):
        response = _client_for(self.user).get(self.page.url)
        self.assertEqual(response.status_code, 403)
        # The refusal is about the feature, not about documentation access.
        self.assertContains(
            response, 'cannot use', status_code=403,
        )

    def test_page_opens_with_the_permission(self):
        user = _grant(self.user, 'screens.view_source')
        self.assertEqual(_client_for(user).get(self.page.url).status_code, 200)

    def test_any_listed_permission_is_enough(self):
        page = registry.get_page(registry.TECHNICAL, 'users-and-teams')
        self.assertGreater(len(page.permissions), 1)
        self.assertFalse(page.require_all)

        user = _grant(self.user, 'helpdocs.view_technical_docs')
        self.assertEqual(_client_for(user).get(page.url).status_code, 403)

        user = _grant(user, 'auth.view_group')
        self.assertEqual(_client_for(user).get(page.url).status_code, 200)

    def test_superuser_sees_everything(self):
        boss = _staff_user('boss3', superuser=True)
        client = _client_for(boss)
        for page in registry.PAGES:
            with self.subTest(slug=f'{page.audience}/{page.slug}'):
                self.assertEqual(client.get(page.url).status_code, 200)

    def test_next_link_skips_a_page_the_reader_cannot_open(self):
        """Bulk upload sits between Content and Playlists; without add_source
        the reader should be handed Playlists, not a page that would 403."""
        user = _grant(
            self.user, 'screens.view_source', 'screens.view_playlist',
        )
        response = _client_for(user).get(self.page.url)
        bulk = registry.get_page(registry.USERS, 'content-bulk-upload')
        playlists = registry.get_page(registry.USERS, 'playlists')
        self.assertNotContains(response, bulk.url)
        self.assertContains(response, playlists.url)


class SectionPermissionTests(TestCase):
    """`{% if perms.x.y %}` inside a page hides part of it."""

    def setUp(self):
        self.user = _staff_user('editor2')
        self.page = registry.get_page(registry.USERS, 'content')

    def test_section_hidden_without_the_permission(self):
        user = _grant(self.user, 'screens.view_source')
        response = _client_for(user).get(self.page.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Deleting content')

    def test_section_shown_with_the_permission(self):
        user = _grant(
            self.user, 'screens.view_source', 'screens.delete_source',
        )
        response = _client_for(user).get(self.page.url)
        self.assertContains(response, 'Deleting content')

    def test_hidden_section_is_absent_from_the_contents_list(self):
        """The on-page table of contents is built from the rendered HTML, so a
        hidden section must not leave an entry pointing at nothing."""
        user = _grant(self.user, 'screens.view_source')
        response = _client_for(user).get(self.page.url)
        self.assertNotContains(response, '#deleting-content')

    def test_render_cache_is_not_shared_between_readers(self):
        """Both variants are rendered in one process; the second must not be
        served the first one's HTML."""
        viewer = _grant(_staff_user('viewer'), 'screens.view_source')
        deleter = _grant(
            _staff_user('deleter'),
            'screens.view_source', 'screens.delete_source',
        )

        first = _client_for(viewer).get(self.page.url)
        second = _client_for(deleter).get(self.page.url)
        third = _client_for(viewer).get(self.page.url)

        self.assertNotContains(first, 'Deleting content')
        self.assertContains(second, 'Deleting content')
        self.assertNotContains(third, 'Deleting content')

    def test_rendering_without_a_user_shows_everything(self):
        """check_help_docs and the tests must see the full page."""
        html = rendering.render_page(self.page)['html']
        self.assertIn('Deleting content', html)

    def test_fingerprint_only_covers_referenced_permissions(self):
        source = '# T\n\n{% if perms.screens.delete_source %}x{% endif %}'
        self.assertEqual(
            rendering.permissions_referenced(source),
            ['screens.delete_source'],
        )
        self.assertEqual(rendering.permissions_referenced('# T\n\nplain'), [])


class TickerDocumentationTests(TestCase):
    """The ticker tape is invisible to a reader who cannot use it.

    Being able to view or change screens is not enough — the page and every
    mention of the feature are gated on the two ticker permissions.
    """

    def setUp(self):
        self.user = _staff_user('screen_editor')
        self.page = registry.get_page(registry.USERS, 'ticker-tape')
        self.screens_page = registry.get_page(registry.USERS, 'screens')

    def test_page_is_forbidden_for_a_plain_screen_editor(self):
        user = _grant(self.user, 'screens.view_screen', 'screens.change_screen')
        self.assertEqual(_client_for(user).get(self.page.url).status_code, 403)

    def test_page_is_absent_from_the_index_for_a_plain_screen_editor(self):
        user = _grant(self.user, 'screens.view_screen')
        response = _client_for(user).get(reverse('admin:help_index'))
        self.assertNotContains(response, self.page.url)

    def test_either_ticker_permission_opens_the_page(self):
        for username, permission in (
            ('writer', 'screens.change_ticker_text'),
            ('configurer', 'screens.change_ticker_settings'),
        ):
            with self.subTest(permission=permission):
                user = _grant(
                    _staff_user(username), 'screens.view_screen', permission,
                )
                client = _client_for(user)
                self.assertEqual(client.get(self.page.url).status_code, 200)
                index = client.get(reverse('admin:help_index'))
                self.assertContains(index, self.page.url)

    def test_each_tier_sees_only_its_own_instructions(self):
        writer = _grant(
            _staff_user('writer2'),
            'screens.view_screen', 'screens.change_ticker_text',
        )
        configurer = _grant(
            _staff_user('configurer2'),
            'screens.view_screen', 'screens.change_ticker_settings',
        )

        written = _client_for(writer).get(self.page.url)
        self.assertContains(written, 'Writing the message')
        self.assertNotContains(written, 'Turning it on')

        configured = _client_for(configurer).get(self.page.url)
        self.assertContains(configured, 'Turning it on')
        self.assertNotContains(configured, 'Writing the message')

    def test_screens_page_hides_the_pointer_without_a_ticker_permission(self):
        user = _grant(self.user, 'screens.view_screen')
        response = _client_for(user).get(self.screens_page.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Adding a message bar')

        user = _grant(user, 'screens.change_ticker_text')
        self.assertContains(
            _client_for(user).get(self.screens_page.url), 'Adding a message bar',
        )


class ConfigSubstitutionTests(TestCase):
    """Pages must read configurable values live, not bake them in."""

    @override_settings(MAX_IMG_WIDTH=4321, MAX_IMG_HEIGHT=1234)
    def test_image_limits_come_from_settings(self):
        page = registry.get_page(registry.USERS, 'content')
        html = rendering.render_source(page.path.read_text(), page.audience)['html']
        self.assertIn('4321', html)
        self.assertIn('1234', html)

    @override_settings(ADMIN_SITE_NAME='Signum')
    def test_site_name_comes_from_settings(self):
        page = registry.get_page(registry.USERS, 'concepts')
        html = rendering.render_source(page.path.read_text(), page.audience)['html']
        self.assertIn('Signum', html)

    def test_every_config_reference_is_whitelisted(self):
        known = set(rendering.ALL_CONFIG_KEYS)
        for page in registry.PAGES:
            source = page.path.read_text()
            for match in rendering.CONFIG_REF_RE.finditer(source):
                with self.subTest(slug=page.slug, key=match.group('key')):
                    self.assertIn(match.group('key'), known)


class MarkdownRenderingTests(TestCase):
    def test_help_links_resolve_to_page_urls(self):
        rendered = rendering.render_source(
            '# T\n\n[Go](help:teams)', registry.USERS,
        )
        self.assertIn(registry.get_page(registry.USERS, 'teams').url, rendered['html'])
        self.assertNotIn('help:teams', rendered['html'])

    def test_cross_audience_links_resolve(self):
        rendered = rendering.render_source(
            '# T\n\n[Go](help:technical/access-model)', registry.USERS,
        )
        self.assertIn(
            registry.get_page(registry.TECHNICAL, 'access-model').url,
            rendered['html'],
        )

    def test_broken_help_link_is_left_visible(self):
        rendered = rendering.render_source('# T\n\n[Go](help:nope)', registry.USERS)
        self.assertIn('help:nope', rendered['html'])

    def test_missing_screenshot_becomes_a_placeholder(self):
        rendered = rendering.render_source(
            '# T\n\n![Alt](screenshot:definitely-not-captured)', registry.USERS,
        )
        self.assertIn('help-screenshot-missing', rendered['html'])

    def test_captured_screenshot_becomes_a_figure(self):
        name = 'dashboard'
        if rendering.screenshot_url(name) is None:
            self.skipTest('screenshots have not been captured in this checkout')
        rendered = rendering.render_source(
            f'# T\n\n![The dashboard](screenshot:{name})', registry.USERS,
        )
        self.assertIn('<figure', rendered['html'])
        self.assertIn('<figcaption>The dashboard</figcaption>', rendered['html'])

    def test_title_comes_from_the_first_heading(self):
        rendered = rendering.render_source('# The Title\n\nBody.', registry.USERS)
        self.assertEqual(rendered['title'], 'The Title')


class ContextualHelpLinkTests(TestCase):
    """The "?" injected above mapped admin changelists."""

    def setUp(self):
        self.user = _staff_user('editor')
        for permission in Permission.objects.filter(
            content_type__app_label='screens'
        ):
            self.user.user_permissions.add(permission)
        self.user = User.objects.get(pk=self.user.pk)

    def test_hint_appears_on_a_mapped_changelist(self):
        response = _client_for(self.user).get(
            reverse('admin:screens_playlist_changelist')
        )
        self.assertContains(
            response, registry.get_page(registry.USERS, 'playlists').url,
        )

    def test_slot_template_emits_no_stray_text(self):
        """The slot partial is included on most admin pages, so anything it
        leaks appears everywhere. A multi-line `{# #}` comment is not a comment
        in Django and is rendered as literal text — that regression shipped
        once."""
        for url_name in (
            'admin:screens_playlist_changelist',
            'admin:screens_source_changelist',
            'admin:screens_screen_changelist',
        ):
            response = _client_for(self.user).get(reverse(url_name))
            with self.subTest(url_name=url_name):
                self.assertNotContains(response, 'attach_help_links')
                self.assertNotContains(response, 'list_before_template')
                self.assertNotContains(response, '{#')
                self.assertNotContains(response, 'endcomment')

    def test_hint_absent_where_nothing_is_mapped(self):
        superuser = _staff_user('boss2', superuser=True)
        response = _client_for(superuser).get(
            reverse('admin:django_celery_beat_intervalschedule_changelist')
        )
        self.assertNotContains(response, 'admin/help/users/')

    def test_hint_hidden_when_the_audience_is_out_of_reach(self):
        """A user without technical access sees no link to a technical page."""
        for permission in Permission.objects.filter(
            content_type__app_label='auth', codename__endswith='_user'
        ):
            self.user.user_permissions.add(permission)
        self.user = User.objects.get(pk=self.user.pk)

        response = _client_for(self.user).get(reverse('admin:auth_user_changelist'))
        technical_page = registry.get_page(registry.TECHNICAL, 'users-and-teams')
        self.assertNotContains(response, technical_page.url)

    def test_room_admin_hint_follows_technical_permission(self):
        """Room displays are technical-only, so an operator who can edit rooms
        still gets no link unless they can read the technical set."""
        for permission in Permission.objects.filter(
            content_type__app_label='room_schedules'
        ):
            self.user.user_permissions.add(permission)
        self.user = User.objects.get(pk=self.user.pk)

        page = registry.get_page(registry.TECHNICAL, 'room-displays')
        url = reverse('admin:room_schedules_room_changelist')

        response = _client_for(self.user).get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, page.url)

        self.user.user_permissions.add(
            Permission.objects.get(codename='view_technical_docs')
        )
        self.user = User.objects.get(pk=self.user.pk)
        self.assertContains(_client_for(self.user).get(url), page.url)


class DashboardHelpPanelTests(TestCase):
    def test_getting_started_steps_link_to_real_pages(self):
        user = _staff_user('dash')
        response = _client_for(user).get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Getting started')
        for slug in ('getting-started', 'teams', 'content', 'playlists',
                     'schedules', 'screens'):
            page = registry.get_page(registry.USERS, slug)
            self.assertIsNotNone(page, f'dashboard links to missing page {slug}')
            self.assertContains(response, page.url)


class RegistryTests(TestCase):
    def test_every_page_has_a_file(self):
        for page in registry.PAGES:
            with self.subTest(slug=f'{page.audience}/{page.slug}'):
                self.assertTrue(page.path.exists(), f'missing {page.path}')

    def test_every_audience_has_an_intro(self):
        for audience in registry.AUDIENCES:
            self.assertTrue(registry.intro_path(audience).exists())

    def test_every_file_is_listed(self):
        listed = {(p.audience, p.slug) for p in registry.PAGES}
        for audience in registry.AUDIENCES:
            for path in (registry.CONTENT_ROOT / audience).glob('*.md'):
                if path.stem == 'index':
                    continue
                with self.subTest(path=str(path)):
                    self.assertIn((audience, path.stem), listed)

    def test_sections_cover_every_page(self):
        for audience in registry.AUDIENCES:
            grouped = registry.sections_for(audience)
            flat = [p for _, pages in grouped for p in pages]
            self.assertCountEqual(flat, registry.pages_for(audience))
