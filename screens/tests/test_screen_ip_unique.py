"""Two screens may not share an IP address.

A device finds its screen by address and plays whichever match the database
returns first, so a second screen on the same IP silently takes the device
over from the first, or is silently ignored by it.
"""

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from estate.tests.helpers import grant_all_locations
from estate.tests.test_estate_admin import _perms
from screens.models import Playlist, Schedule, Screen, Team


class ScreenIpUniqueTests(TestCase):
    def setUp(self):
        Team.objects.all().delete()
        self.team = Team.objects.create(name="Alpha")
        self.other_team = Team.objects.create(name="Beta")
        playlist = Playlist.objects.create(name="p")
        playlist.teams.add(self.team)
        self.schedule = Schedule.objects.create(name="s", default_playlist=playlist)
        self.schedule.teams.add(self.team)

        self.foyer = self._screen("Foyer", "10.0.0.1", self.team)
        self.library = self._screen("Library", "10.0.0.2", self.team)

        user = User.objects.create_user('ed', 'e@x', 'pw', is_staff=True)
        grant_all_locations(user)
        user.teams.add(self.team)
        user.user_permissions.add(*_perms(
            Screen, 'view_screen', 'add_screen', 'change_screen'))
        self.client = Client()
        self.client.force_login(user)
        self.client.get(reverse('admin:index'))  # initialise the active-team session

    def _screen(self, name, ip, team):
        screen = Screen.objects.create(name=name, ip=ip, schedule=self.schedule)
        screen.teams.add(team)
        return screen

    def _fields(self, **fields):
        return {
            'name': 'New', 'ip': '10.0.0.99',
            'schedule': str(self.schedule.pk),
            'interspersed_playlist': '', 'interspersed_rate': '1',
            **fields,
        }

    def _add(self, **fields):
        return self.client.post(reverse('admin:screens_screen_add'),
                                self._fields(**fields))

    def _change(self, screen, **fields):
        return self.client.post(
            reverse('admin:screens_screen_change', args=[screen.pk]),
            self._fields(**{'name': screen.name, 'ip': screen.ip, **fields}))

    def _ip_errors(self, response):
        self.assertEqual(response.status_code, 200)
        return response.context['adminform'].form.errors['ip']

    def test_a_new_address_saves(self):
        """The baseline, so the refusals below are known to be about the IP."""
        self.assertEqual(self._add().status_code, 302)
        self.assertTrue(Screen.objects.filter(ip='10.0.0.99').exists())

    def test_adding_a_screen_on_an_address_in_use_is_refused(self):
        resp = self._add(ip='10.0.0.1')
        self.assertEqual(self._ip_errors(resp), [
            "The screen “Foyer” already uses this IP address. Each device "
            "needs its own address, so correct this one, or change or delete "
            "that screen first."])
        self.assertEqual(Screen.objects.filter(ip='10.0.0.1').count(), 1)

    def test_moving_a_screen_onto_an_address_in_use_is_refused(self):
        resp = self._change(self.library, ip='10.0.0.1')
        self.assertIn("“Foyer”", self._ip_errors(resp)[0])
        self.library.refresh_from_db()
        self.assertEqual(self.library.ip, '10.0.0.2')

    def test_a_screen_keeping_its_own_address_still_saves(self):
        resp = self._change(self.foyer, name="Main foyer")
        self.assertEqual(resp.status_code, 302)
        self.foyer.refresh_from_db()
        self.assertEqual(self.foyer.name, "Main foyer")

    def test_one_address_written_two_ways_is_still_a_clash(self):
        """IPv6 is normalised on both sides, so padding does not slip past."""
        self._screen("Atrium", "2001:db8::1", self.team)
        resp = self._add(ip='2001:0db8:0000:0000:0000:0000:0000:0001')
        self.assertIn("“Atrium”", self._ip_errors(resp)[0])

    def test_a_clash_with_a_screen_the_user_cannot_see_is_refused_unnamed(self):
        """Still refused -- the device does not care about teams -- but the
        other team's screen name is not theirs to read."""
        self._screen("Beta secret", "10.0.0.50", self.other_team)
        resp = self._add(ip='10.0.0.50')
        errors = self._ip_errors(resp)
        self.assertEqual(errors, [
            "Another screen already uses this IP address, outside your current "
            "team or locations. Each device needs its own address — ask an "
            "administrator to find the other screen."])
        self.assertNotContains(resp, "Beta secret")
        self.assertEqual(Screen.objects.filter(ip='10.0.0.50').count(), 1)
