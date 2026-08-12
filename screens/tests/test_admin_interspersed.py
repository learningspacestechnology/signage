"""Admin behaviour for the interspersed playlist fields.

Two separate concerns:

* **Team scoping.** The FK dropdown is narrowed by a name allowlist in
  ``TeamScopedAdminMixin.formfield_for_foreignkey``. Missing an entry there is
  not cosmetic: ``ModelChoiceField`` validates against the same queryset, so an
  unscoped FK lets a hand-crafted POST point one team's screen at another
  team's playlist, whose content then plays indefinitely on a screen the owning
  team cannot see.
* **The ticker guard.** A ticker screen cannot play screen-level interspersed
  content at all (see KNOWN_ISSUES.md), so the fields are hidden and excluded
  rather than left to be set and silently ignored.
"""
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase

from screens.models import (
    Playlist,
    PlaylistEntry,
    PlaylistRelation,
    Schedule,
    Screen,
    Source,
    Team,
)


def _grant_all_model_perms(user, models):
    for model in models:
        ct = ContentType.objects.get_for_model(model)
        user.user_permissions.add(*Permission.objects.filter(content_type=ct))


class InterspersedAdminTests(TestCase):
    def setUp(self):
        Team.objects.all().delete()
        self.team_a = Team.objects.create(name="Alpha")
        self.team_b = Team.objects.create(name="Bravo")

        self.user_a = User.objects.create_user('alice', 'a@x', 'pw', is_staff=True)
        self.user_a.teams.add(self.team_a)
        _grant_all_model_perms(
            self.user_a,
            [Source, Playlist, Screen, Schedule, PlaylistEntry, PlaylistRelation])
        self.superuser = User.objects.create_superuser('root', 'r@x', 'pw')

        self.list_a = Playlist.objects.create(name="listA")
        self.list_a.teams.add(self.team_a)
        self.logo_a = Playlist.objects.create(name="logoA")
        self.logo_a.teams.add(self.team_a)
        self.list_b = Playlist.objects.create(name="listB")
        self.list_b.teams.add(self.team_b)

        self.schedule = Schedule.objects.create(name="sched", default_playlist=self.list_a)
        self.schedule.teams.add(self.team_a)
        self.screen = Screen.objects.create(
            name="Foyer", ip="10.0.0.1", schedule=self.schedule)
        self.screen.teams.add(self.team_a)

        self.screen_url = f'/admin/screens/screen/{self.screen.pk}/change/'

    def _client(self, user):
        client = Client()
        client.force_login(user)
        client.get(self.screen_url)  # initialise the active-team session
        return client

    def _screen_post(self, **overrides):
        payload = {
            'name': 'Foyer',
            'ip': '10.0.0.1',
            'schedule': str(self.schedule.pk),
            'interspersed_playlist': '',
            'interspersed_rate': '1',
            'ticker_enabled': '',
            'ticker_layout': 'OVERLAY',
            'ticker_text': '',
            'ticker_style_preset': 'CLASSIC',
            'ticker_font_size_px': '',
            'ticker_font_color': '',
            'ticker_background_color': '',
            'ticker_background_opacity': '',
            'ticker_scroll_speed_px_sec': '',
        }
        payload.update(overrides)
        return payload

    # --- Team scoping --------------------------------------------------------

    def test_screen_choices_are_scoped_to_the_active_team(self):
        response = self._client(self.user_a).get(self.screen_url)
        choices = response.context['adminform'].form.fields['interspersed_playlist'].queryset
        self.assertIn(self.logo_a, choices)
        self.assertNotIn(self.list_b, choices)

    def test_playlist_choices_are_scoped_to_the_active_team(self):
        response = self._client(self.user_a).get(
            f'/admin/screens/playlist/{self.list_a.pk}/change/')
        choices = response.context['adminform'].form.fields['interspersed_playlist'].queryset
        self.assertIn(self.logo_a, choices)
        self.assertNotIn(self.list_b, choices)

    def test_posting_another_teams_playlist_is_rejected(self):
        client = self._client(self.user_a)
        response = client.post(
            self.screen_url,
            self._screen_post(interspersed_playlist=str(self.list_b.pk)))

        self.assertEqual(response.status_code, 200)  # redisplayed with an error
        self.screen.refresh_from_db()
        self.assertIsNone(self.screen.interspersed_playlist)

    def test_a_user_can_set_a_playlist_from_their_own_team(self):
        client = self._client(self.user_a)
        response = client.post(
            self.screen_url,
            self._screen_post(interspersed_playlist=str(self.logo_a.pk)))

        self.assertEqual(response.status_code, 302)
        self.screen.refresh_from_db()
        self.assertEqual(self.screen.interspersed_playlist, self.logo_a)

    def test_a_superuser_may_pick_any_playlist(self):
        client = Client()
        client.force_login(self.superuser)
        client.get(self.screen_url)
        response = client.get(self.screen_url)
        choices = response.context['adminform'].form.fields['interspersed_playlist'].queryset
        self.assertIn(self.list_b, choices)

    # --- The ticker guard ----------------------------------------------------

    def test_the_fields_are_shown_while_the_ticker_is_off(self):
        response = self._client(self.superuser).get(self.screen_url)
        fields = response.context['adminform'].form.fields
        self.assertIn('interspersed_playlist', fields)
        self.assertIn('interspersed_rate', fields)

    def test_the_fields_are_hidden_once_the_ticker_is_on(self):
        self.screen.ticker_enabled = True
        self.screen.save()
        response = self._client(self.superuser).get(self.screen_url)
        fields = response.context['adminform'].form.fields
        self.assertNotIn('interspersed_playlist', fields)
        self.assertNotIn('interspersed_rate', fields)

    def test_an_explanation_replaces_the_hidden_fields(self):
        """Vanishing without a word is worse than the trap it prevents — a user
        without ticker permissions would see no reason for the gap."""
        self.screen.ticker_enabled = True
        self.screen.save()
        response = self._client(self.superuser).get(self.screen_url)
        self.assertContains(response, 'Not available while the ticker is turned on')

    def test_a_ticker_screen_ignores_an_interspersed_playlist_posted_by_hand(self):
        self.screen.ticker_enabled = True
        self.screen.save()
        # user_a rather than the superuser: teams is excluded from their form,
        # so the payload above is complete. Asserting the 302 matters — a
        # rejected POST would otherwise look just like a correctly-ignored field.
        client = self._client(self.user_a)
        response = client.post(self.screen_url, self._screen_post(
            ticker_enabled='on',
            interspersed_playlist=str(self.logo_a.pk)))

        self.assertEqual(response.status_code, 302)
        self.screen.refresh_from_db()
        self.assertIsNone(self.screen.interspersed_playlist)

    def test_a_stored_playlist_survives_the_ticker_being_turned_on(self):
        """Hidden, not cleared, so turning the ticker off restores it.

        The save that enables the ticker still renders the fields (the stored
        screen has no ticker yet), so a browser submits the selected playlist
        back. Every save afterwards omits them entirely — that is the one that
        has to leave the stored value alone.
        """
        self.screen.interspersed_playlist = self.logo_a
        self.screen.save()
        client = self._client(self.user_a)

        response = client.post(self.screen_url, self._screen_post(
            ticker_enabled='on', interspersed_playlist=str(self.logo_a.pk)))
        self.assertEqual(response.status_code, 302)
        self.screen.refresh_from_db()
        self.assertTrue(self.screen.ticker_enabled)
        self.assertEqual(self.screen.interspersed_playlist, self.logo_a)

        # The fields are no longer on the form, so a real submission has no such
        # keys at all.
        without_interspersed = self._screen_post(ticker_enabled='on', name='Renamed')
        del without_interspersed['interspersed_playlist']
        del without_interspersed['interspersed_rate']
        response = client.post(self.screen_url, without_interspersed)
        self.assertEqual(response.status_code, 302)
        self.screen.refresh_from_db()
        self.assertEqual(self.screen.name, 'Renamed')
        self.assertEqual(self.screen.interspersed_playlist, self.logo_a)

        response = client.post(self.screen_url, self._screen_post(
            name='Renamed', ticker_enabled='',
            interspersed_playlist=str(self.logo_a.pk)))
        self.assertEqual(response.status_code, 302)
        self.screen.refresh_from_db()
        self.assertFalse(self.screen.ticker_enabled)
        self.assertEqual(self.screen.interspersed_playlist, self.logo_a)
