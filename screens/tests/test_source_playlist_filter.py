from django.contrib.auth.models import Permission, User
from django.test import Client, TestCase

from screens.models import Playlist, PlaylistEntry, Source, Team


class NotInAnyPlaylistFilterTests(TestCase):
    """The content list's "In Playlist" filter can find content in no playlist."""

    def setUp(self):
        Team.objects.all().delete()
        self.alpha = Team.objects.create(name="Alpha")
        self.bravo = Team.objects.create(name="Bravo")

        self.operator = User.objects.create_user('alice', 'a@x', 'pw', is_staff=True)
        self.operator.teams.add(self.alpha)
        self.operator.user_permissions.add(
            *Permission.objects.filter(content_type__app_label='screens',
                                       codename__endswith='_source'))
        self.root = User.objects.create_superuser('root', 'r@x', 'pw')

        self.posters = Playlist.objects.create(name="posters")
        self.posters.teams.add(self.alpha)
        self.bravo_list = Playlist.objects.create(name="bravo-list")
        self.bravo_list.teams.add(self.bravo)

        self.used = self.source("used-src", self.alpha)
        self.unused = self.source("unused-src", self.alpha)
        # Alpha's content, but only in a playlist Alpha cannot see.
        self.lent = self.source("lent-src", self.alpha)
        self.other_unused = self.source("bravo-unused-src", self.bravo)

        PlaylistEntry.objects.create(playlist=self.posters, source=self.used, number=1)
        PlaylistEntry.objects.create(playlist=self.bravo_list, source=self.lent, number=1)

    @staticmethod
    def source(name, team):
        source = Source.objects.create(type=Source.IFRAME, name=name, url="http://x")
        source.teams.add(team)
        return source

    def listed(self, user, query):
        client = Client()
        client.force_login(user)
        response = client.get(f'/admin/screens/source/?{query}')
        self.assertEqual(response.status_code, 200)
        return {s.name for s in response.context['cl'].result_list}

    def test_lists_only_content_in_no_playlist(self):
        self.assertEqual(self.listed(self.operator, 'playlist=none'), {"unused-src"})

    def test_content_in_another_teams_playlist_does_not_count_as_unused(self):
        self.assertNotIn("lent-src", self.listed(self.operator, 'playlist=none'))

    def test_stays_scoped_to_the_active_team(self):
        self.assertEqual(self.listed(self.root, 'playlist=none'),
                         {"unused-src", "bravo-unused-src"})
        self.assertNotIn("bravo-unused-src", self.listed(self.operator, 'playlist=none'))

    def test_removing_the_last_entry_makes_content_unused(self):
        PlaylistEntry.objects.filter(source=self.used).delete()
        self.assertIn("used-src", self.listed(self.operator, 'playlist=none'))

    def test_offered_as_the_first_choice(self):
        client = Client()
        client.force_login(self.operator)
        response = client.get('/admin/screens/source/')
        self.assertContains(response, "Not in any playlist")

    def test_filtering_by_one_playlist_still_works(self):
        self.assertEqual(self.listed(self.operator, f'playlist={self.posters.pk}'),
                         {"used-src"})
