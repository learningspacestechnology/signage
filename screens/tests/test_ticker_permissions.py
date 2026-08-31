"""The ticker tape is gated by two grantable permissions, not by the staff flag.

``screens.change_ticker_settings`` covers turning the ticker on and choosing its
layout; ``screens.change_ticker_text`` covers the message and its styling. A user
holding neither must see no ticker fields at all — and, more importantly, must not
be able to write them with a hand-crafted POST, which is what ``get_exclude``
buys over ``get_fieldsets``.
"""
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase

from screens.models import Playlist, Schedule, Screen, Team

GATE_FIELDS = ('ticker_enabled', 'ticker_layout')
TEXT_FIELDS = (
    'ticker_text', 'ticker_style_preset',
    'ticker_font_size_px', 'ticker_font_color',
    'ticker_background_color', 'ticker_background_opacity',
    'ticker_scroll_speed_px_sec',
)


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


class TickerPermissionTests(TestCase):
    def setUp(self):
        Team.objects.all().delete()
        self.team = Team.objects.create(name="Alpha")
        self.playlist = Playlist.objects.create(name="list")
        self.playlist.teams.add(self.team)
        self.schedule = Schedule.objects.create(
            name="sched", default_playlist=self.playlist,
        )
        self.schedule.teams.add(self.team)

        self.screen = Screen.objects.create(
            name="Foyer", ip="10.0.0.1", schedule=self.schedule,
        )
        self.screen.teams.add(self.team)

        self.url = f'/admin/screens/screen/{self.screen.pk}/change/'

    def _editor(self, username, *perms):
        """A staff user who can change screens, plus any extra permissions."""
        user = User.objects.create_user(username, f'{username}@x', 'pw', is_staff=True)
        user.teams.add(self.team)
        screen_ct = ContentType.objects.get_for_model(Screen)
        user.user_permissions.add(
            *Permission.objects.filter(
                content_type=screen_ct,
                codename__in=('view_screen', 'change_screen', 'add_screen'),
            )
        )
        return _grant(user, *perms) if perms else User.objects.get(pk=user.pk)

    def _form(self, user):
        client = Client()
        client.force_login(user)
        response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response

    def _assert_fields(self, response, present=(), absent=()):
        for field in present:
            self.assertContains(response, f'name="{field}"', msg_prefix=field)
        for field in absent:
            self.assertNotContains(response, f'name="{field}"', msg_prefix=field)

    # --- Visibility on the change form ---------------------------------------

    def test_plain_screen_editor_sees_no_ticker_fields(self):
        response = self._form(self._editor('plain'))
        self._assert_fields(response, absent=GATE_FIELDS + TEXT_FIELDS)
        self.assertNotContains(response, 'Ticker tape')

    def test_text_permission_shows_only_the_message_fields(self):
        user = self._editor('writer', 'screens.change_ticker_text')
        response = self._form(user)
        self._assert_fields(response, present=TEXT_FIELDS, absent=GATE_FIELDS)
        self.assertContains(response, 'Ticker tape')

    def test_settings_permission_shows_only_the_enable_and_layout_fields(self):
        user = self._editor('configurer', 'screens.change_ticker_settings')
        response = self._form(user)
        self._assert_fields(response, present=GATE_FIELDS, absent=TEXT_FIELDS)
        self.assertContains(response, 'Ticker tape')

    def test_both_permissions_show_every_field(self):
        user = self._editor(
            'both', 'screens.change_ticker_settings', 'screens.change_ticker_text',
        )
        self._assert_fields(self._form(user), present=GATE_FIELDS + TEXT_FIELDS)

    def test_superuser_sees_every_field(self):
        user = User.objects.create_superuser('root', 'r@x', 'pw')
        self._assert_fields(self._form(user), present=GATE_FIELDS + TEXT_FIELDS)

    # --- The fields are excluded from the form, not merely hidden -------------

    def test_plain_editor_cannot_write_ticker_fields_by_post(self):
        user = self._editor('crafty')
        client = Client()
        client.force_login(user)
        client.get(self.url)  # initialise the active-team session

        response = client.post(self.url, {
            'name': 'Foyer',
            'ip': '10.0.0.1',
            'schedule': str(self.schedule.pk),
            'interspersed_playlist': '',
            'interspersed_rate': '1',
            # Not on this user's form; the admin must ignore them.
            'ticker_enabled': 'on',
            'ticker_layout': 'SHRINK',
            'ticker_text': 'injected',
        })
        self.assertEqual(response.status_code, 302)

        self.screen.refresh_from_db()
        self.assertFalse(self.screen.ticker_enabled)
        self.assertEqual(self.screen.ticker_text, '')
        self.assertEqual(self.screen.ticker_layout, 'OVERLAY')

    def test_text_holder_cannot_enable_the_ticker_by_post(self):
        user = self._editor('writer2', 'screens.change_ticker_text')
        client = Client()
        client.force_login(user)
        client.get(self.url)

        response = client.post(self.url, {
            'name': 'Foyer',
            'ip': '10.0.0.1',
            'schedule': str(self.schedule.pk),
            'interspersed_playlist': '',
            'interspersed_rate': '1',
            'ticker_text': 'Library closes at 6pm',
            'ticker_style_preset': 'CLASSIC',
            'ticker_font_size_px': '',
            'ticker_font_color': '',
            'ticker_background_color': '',
            'ticker_background_opacity': '',
            'ticker_scroll_speed_px_sec': '',
            # Beyond this user's tier.
            'ticker_enabled': 'on',
        })
        self.assertEqual(response.status_code, 302)

        self.screen.refresh_from_db()
        self.assertEqual(self.screen.ticker_text, 'Library closes at 6pm')
        self.assertFalse(self.screen.ticker_enabled)
