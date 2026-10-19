from django.contrib.auth.models import Group, Permission, User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from advertising.password_auth import password_login_enabled
from screens.models import Team, TeamMembership

ENTRA_BACKEND = "advertising.entra_auth.EntraOIDCBackend"

# Microsoft sign-in counts as usable only when enabled *and* given a client ID;
# without both, PASSWORD_LOGIN_ENABLED=False is ignored.
PASSWORDS_OFF = override_settings(
    PASSWORD_LOGIN_ENABLED=False, ENTRA_AUTH_ENABLED=True, ENTRA_CLIENT_ID="x")


class PasswordLoginTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="svc", password="pw", is_staff=True)
        # Staff with no team get a 403 from ActiveTeamMiddleware.
        self.team = Team.objects.create(name="Signage")
        TeamMembership.objects.create(user=self.user, team=self.team)

    def _post_login(self):
        return self.client.post(
            reverse("admin:login"), {"username": "svc", "password": "pw"})

    @override_settings(PASSWORD_LOGIN_ENABLED=True, ENTRA_AUTH_ENABLED=True,
                       ENTRA_CLIENT_ID="x")
    def test_password_login_works_when_enabled(self):
        self.assertTrue(self.client.login(username="svc", password="pw"))

    @PASSWORDS_OFF
    def test_password_login_refused_when_disabled(self):
        self.assertFalse(self.client.login(username="svc", password="pw"))

    @PASSWORDS_OFF
    def test_admin_login_post_creates_no_session_when_disabled(self):
        # The form is gone from the page, but a hand-built POST must fail too.
        resp = self._post_login()
        self.assertEqual(resp.status_code, 200)  # re-rendered with an error
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_disabling_ends_existing_password_sessions(self):
        self.assertTrue(self.client.login(username="svc", password="pw"))
        self.assertEqual(self.client.get("/admin/").status_code, 200)

        with PASSWORDS_OFF:
            resp = self.client.get("/admin/")
        self.assertRedirects(
            resp, f"{reverse('admin:login')}?next=/admin/",
            fetch_redirect_response=False)

    @PASSWORDS_OFF
    def test_entra_sessions_survive_and_keep_group_permissions(self):
        # PasswordBackend is ModelBackend underneath, which answers has_perm
        # for every user. Gating that on the setting would strip Entra users
        # of every permission they hold through a Group.
        group = Group.objects.create(name="Viewers")
        group.permissions.add(Permission.objects.get(
            content_type__app_label="screens", codename="view_screen"))
        entra_user = User.objects.create_user(
            username="alice@example.com", is_staff=True)
        entra_user.set_unusable_password()
        entra_user.save()
        entra_user.groups.add(group)
        TeamMembership.objects.create(user=entra_user, team=self.team)

        self.client.force_login(entra_user, backend=ENTRA_BACKEND)
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        self.assertTrue(
            User.objects.get(pk=entra_user.pk).has_perm("screens.view_screen"))

    @override_settings(PASSWORD_LOGIN_ENABLED=False, ENTRA_AUTH_ENABLED=False,
                       ENTRA_CLIENT_ID="x")
    def test_ignored_when_entra_disabled(self):
        self.assertTrue(password_login_enabled())
        self.assertTrue(self.client.login(username="svc", password="pw"))

    @override_settings(PASSWORD_LOGIN_ENABLED=False, ENTRA_AUTH_ENABLED=True,
                       ENTRA_CLIENT_ID="")
    def test_ignored_when_entra_has_no_client_id(self):
        self.assertTrue(password_login_enabled())
        self.assertTrue(self.client.login(username="svc", password="pw"))
