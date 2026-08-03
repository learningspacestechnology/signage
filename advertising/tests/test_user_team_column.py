"""The Users changelist shows team membership and can be filtered by it."""

from django.contrib.auth.models import User
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from screens.models import Team, TeamMembership


class UserTeamColumnTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username="root", email="root@example.com", password="rootpw"
        )
        self.marketing = Team.objects.create(name="Marketing")
        self.library = Team.objects.create(name="Library")

        self.both = User.objects.create_user("both", "both@example.com", is_staff=True)
        TeamMembership.objects.create(user=self.both, team=self.marketing)
        TeamMembership.objects.create(user=self.both, team=self.library)

        self.orphan = User.objects.create_user("orphan", "orphan@x.com", is_staff=True)

        self.client.force_login(self.admin)
        self.url = reverse("admin:auth_user_changelist")

    def test_column_lists_every_team_the_user_belongs_to(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn("Library, Marketing", html)

    def test_column_marks_a_user_with_no_team(self):
        row = self._row_for(self.orphan)
        self.assertIn("—", row)

    def test_filtering_by_team_narrows_the_list(self):
        resp = self.client.get(self.url, {"teams__id__exact": self.marketing.pk})
        usernames = {u.username for u in resp.context["cl"].result_list}
        self.assertEqual(usernames, {"both"})

    def test_filtering_to_users_with_no_team(self):
        resp = self.client.get(self.url, {"teams__isnull": "True"})
        usernames = {u.username for u in resp.context["cl"].result_list}
        self.assertEqual(usernames, {"root", "orphan"})

    def test_the_no_team_option_is_labelled(self):
        resp = self.client.get(self.url)
        cl = resp.context["cl"]
        team_filter = [f for f in cl.filter_specs if f.title == "team"][0]
        self.assertIn("No team", [c["display"] for c in team_filter.choices(cl)])

    def test_a_user_in_two_teams_is_listed_once(self):
        # Filtering across a multi-valued relation duplicates rows without the
        # distinct() the changelist applies for us.
        resp = self.client.get(self.url, {"teams__id__exact": self.marketing.pk})
        self.assertEqual(len(resp.context["cl"].result_list), 1)

    def test_column_does_not_query_per_row(self):
        # The column reads each row's teams, so without the prefetch on the
        # changelist queryset this grows with the number of users.
        self.client.get(self.url)  # warm the content-type cache the first hit fills
        before = self._query_count()
        for i in range(5):
            extra = User.objects.create_user(f"extra{i}", f"e{i}@x.com")
            TeamMembership.objects.create(user=extra, team=self.library)
        self.assertEqual(self._query_count(), before)

    def _query_count(self):
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(self.url)
        return len(ctx)

    def _row_for(self, user):
        html = self.client.get(self.url).content.decode()
        start = html.index(f"/admin/auth/user/{user.pk}/change/")
        cell = html.index('class="field-show_teams', start)
        return html[cell:html.index("</td>", cell)]
