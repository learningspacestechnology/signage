"""The screen form carries no embedded preview of the player.

It showed what the schedule says the screen *should* display, on the page
operators open to learn what the screen *is* displaying, and was read as the
latter. View on site stays as the deliberate way to check the configuration.
Content keeps its preview: there it shows the file itself, which is exactly
what it claims to.
"""
from django.contrib.auth.models import User
from django.test import Client, TestCase

from screens.models import Playlist, Schedule, Screen, Source, Team


class ScreenFormPreviewTests(TestCase):
    def setUp(self):
        team = Team.objects.create(name="Alpha")
        playlist = Playlist.objects.create(name="listA")
        playlist.teams.add(team)
        schedule = Schedule.objects.create(name="sched", default_playlist=playlist)
        schedule.teams.add(team)
        self.screen = Screen.objects.create(name="foyer", ip="10.0.0.1", schedule=schedule)
        self.screen.teams.add(team)
        self.source = Source.objects.create(type=Source.IFRAME, name="web", url="http://x")
        self.source.teams.add(team)

        self.client = Client()
        self.client.force_login(User.objects.create_superuser('root', 'r@x', 'pw'))

    def test_screen_form_has_no_embedded_player(self):
        response = self.client.get(f'/admin/screens/screen/{self.screen.pk}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('screen_preview', response.context['adminform'].readonly_fields)
        self.assertNotContains(response, f'<iframe src="{self.screen.get_absolute_url()}"')

    def test_screen_form_still_offers_view_on_site(self):
        response = self.client.get(f'/admin/screens/screen/{self.screen.pk}/change/')
        self.assertContains(response, '/admin/r/')
        self.assertTrue(response.context['has_absolute_url'])

    def test_content_form_keeps_its_preview(self):
        response = self.client.get(f'/admin/screens/source/{self.source.pk}/change/')
        self.assertIn('image_preview', response.context['adminform'].readonly_fields)
