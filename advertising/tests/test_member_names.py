"""Members by name: the Teams and Location groups admins, and the user page.

A username is a sign-in address, so these pages list and pick people by name
instead. See `advertising.user_picker`.
"""

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from estate.models import LocationGroup, LocationGroupMembership
from estate.tests.helpers import grant_all_locations
from screens.models import Team, TeamMembership


def _person(uun, first="", last=""):
    return User.objects.create_user(
        f"{uun}@ed.ac.uk", f"{uun}@ed.ac.uk", first_name=first, last_name=last,
        is_staff=True)


class PeopleTestCase(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser("root", "root@example.com", "pw")
        self.jane = _person("s1111111", "Jane", "Smith")
        self.jane_doe = _person("s2222222", "Jane", "Doe")
        self.john = _person("s3333333", "John", "Smith")
        self.nameless = _person("s4444444")
        self.client.force_login(self.root)


class MemberListChecks:
    """Run against both changelists by the two subclasses below."""

    changelist = None

    def make_group(self, name, members):
        raise NotImplementedError

    def setUp(self):
        super().setUp()
        self.library = self.make_group("Library", [self.jane, self.nameless])
        self.marketing = self.make_group("Marketing", [self.jane_doe, self.john])

    def _list(self, **params):
        return self.client.get(reverse(self.changelist), params).context["cl"]

    def _found(self, q):
        return [group.name for group in self._list(q=q).result_list]

    def test_members_are_listed_by_name_or_else_username(self):
        cl = self._list()
        rows = {group.name: group for group in cl.result_list}
        # Surname order, so a member with no name yet comes first.
        self.assertEqual(cl.model_admin.show_members(rows["Library"]),
                         "s4444444@ed.ac.uk, Jane Smith")
        self.assertEqual(cl.model_admin.show_members(rows["Marketing"]),
                         "Jane Doe, John Smith")

    def test_a_group_with_no_members_says_so(self):
        self.make_group("Empty", [])
        cl = self._list(q="Empty")
        [row] = cl.result_list
        self.assertEqual(cl.model_admin.show_members(row), "—")

    def test_the_names_column_reads_the_prefetch(self):
        cl = self._list()
        with self.assertNumQueries(0):
            for row in cl.result_list:
                cl.model_admin.show_members(row)

    def test_search_finds_a_group_by_a_members_first_or_last_name(self):
        self.assertEqual(self._found("Doe"), ["Marketing"])
        self.assertEqual(self._found("Smith"), ["Library", "Marketing"])
        self.assertEqual(self._found("john"), ["Marketing"])

    def test_search_finds_a_group_by_a_members_address(self):
        self.assertEqual(self._found("s4444444"), ["Library"])

    def test_a_full_name_must_match_one_member(self):
        # Marketing holds a Jane and a Smith, but not Jane Smith.
        self.assertEqual(self._found("Jane Smith"), ["Library"])

    def test_the_group_name_is_still_searched(self):
        self.assertEqual(self._found("Libr"), ["Library"])

    def test_a_group_with_several_matching_members_is_listed_once(self):
        self.assertEqual(self._found("ed.ac.uk"), ["Library", "Marketing"])


class TeamListTests(MemberListChecks, PeopleTestCase):
    changelist = "admin:screens_team_changelist"

    def make_group(self, name, members):
        team = Team.objects.create(name=name)
        for user in members:
            TeamMembership.objects.create(user=user, team=team)
        return team


class LocationGroupListTests(MemberListChecks, PeopleTestCase):
    changelist = "admin:estate_locationgroup_changelist"

    def make_group(self, name, members):
        group = LocationGroup.objects.create(name=name)
        for user in members:
            LocationGroupMembership.objects.create(user=user, group=group)
        return group


class GroupPickerTests(PeopleTestCase):
    """Picking a team or location group on a user's page matches the name only."""

    def setUp(self):
        super().setUp()
        team = Team.objects.create(name="Library")
        TeamMembership.objects.create(user=self.jane, team=team)
        group = LocationGroup.objects.create(name="Library buildings")
        LocationGroupMembership.objects.create(user=self.jane, group=group)

    def _pick(self, app_label, model_name, term):
        resp = self.client.get(reverse("admin:autocomplete"), {
            "app_label": app_label, "model_name": model_name,
            "field_name": "team" if app_label == "screens" else "group",
            "term": term,
        })
        self.assertEqual(resp.status_code, 200)
        return [r["text"] for r in resp.json()["results"]]

    def test_the_team_picker_ignores_member_names(self):
        self.assertEqual(self._pick("screens", "teammembership", "Smith"), [])
        self.assertEqual(self._pick("screens", "teammembership", "Lib"), ["Library"])

    def test_the_location_group_picker_ignores_member_names(self):
        self.assertEqual(self._pick("estate", "locationgroupmembership", "Smith"), [])
        self.assertEqual(self._pick("estate", "locationgroupmembership", "Lib"),
                         ["Library buildings"])


class UserPickerTests(PeopleTestCase):
    """The member picker on a team or location group page."""

    def _pick(self, term, field_name="user", client=None):
        return (client or self.client).get(reverse("admin:user_picker"), {
            "app_label": "screens", "model_name": "teammembership",
            "field_name": field_name, "term": term,
        })

    def _texts(self, term):
        resp = self._pick(term)
        self.assertEqual(resp.status_code, 200)
        return sorted(r["text"] for r in resp.json()["results"])

    def test_results_are_labelled_by_name_then_address(self):
        self.assertEqual(self._texts("Smith"), [
            "Jane Smith (s1111111@ed.ac.uk)",
            "John Smith (s3333333@ed.ac.uk)",
        ])

    def test_a_user_with_no_name_is_labelled_by_address(self):
        self.assertEqual(self._texts("s4444444"), ["s4444444@ed.ac.uk"])

    def test_it_only_serves_users(self):
        Team.objects.create(name="Library")
        self.assertEqual(self._pick("Lib", field_name="team").status_code, 403)

    def test_it_needs_permission_to_view_users(self):
        staff = _person("s5555555")
        TeamMembership.objects.create(user=staff, team=Team.objects.create(name="T"))
        client = self.client_class()
        client.force_login(staff)
        self.assertEqual(self._pick("Smith", client=client).status_code, 403)

    def test_member_rows_show_the_name(self):
        team = Team.objects.create(name="Library")
        TeamMembership.objects.create(user=self.jane, team=team)
        group = LocationGroup.objects.create(name="Library buildings")
        LocationGroupMembership.objects.create(user=self.jane, group=group)
        for url, caption in (
                (reverse("admin:screens_team_change", args=[team.pk]),
                 "Jane Smith ∈ Library"),
                (reverse("admin:estate_locationgroup_change", args=[group.pk]),
                 "Jane Smith ∈ Library buildings")):
            with self.subTest(url=url):
                resp = self.client.get(url)
                # The picker's selected option, and the caption over the row.
                self.assertContains(resp, "Jane Smith (s1111111@ed.ac.uk)")
                self.assertContains(resp, caption)


class UserPageTests(PeopleTestCase):
    """A user's change page shows their teams and location groups."""

    def setUp(self):
        super().setUp()
        self.team = Team.objects.create(name="Library")
        TeamMembership.objects.create(user=self.jane, team=self.team)
        group = LocationGroup.objects.create(name="Library buildings")
        LocationGroupMembership.objects.create(user=self.jane, group=group)
        self.url = reverse("admin:auth_user_change", args=[self.jane.pk])

    def test_a_superuser_can_edit_both_memberships(self):
        resp = self.client.get(self.url)
        self.assertContains(resp, "teammembership_set-TOTAL_FORMS")
        self.assertContains(resp, "location_group_memberships-TOTAL_FORMS")
        self.assertNotContains(resp, "Only superusers can change these.")

    def test_anyone_else_sees_them_read_only(self):
        editor = _person("s6666666")
        TeamMembership.objects.create(user=editor, team=self.team)
        grant_all_locations(editor)
        editor.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="auth", codename__in=("view_user", "change_user")))
        self.client.force_login(editor)
        resp = self.client.get(self.url)
        self.assertContains(resp, "Only superusers can change these.")
        self.assertContains(resp, "Library buildings")
        self.assertNotContains(resp, "teammembership_set-TOTAL_FORMS")
        self.assertNotContains(resp, "location_group_memberships-TOTAL_FORMS")
