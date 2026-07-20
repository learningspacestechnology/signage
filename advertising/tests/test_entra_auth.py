from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from advertising.entra_auth import EntraOIDCBackend
from screens.models import Team, TeamMembership

CLAIMS = {
    "preferred_username": "Alice@example.com",
    "name": "Alice Smith",
    "oid": "00000000-0000-0000-0000-000000000001",
}


class EntraBackendTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.backend = EntraOIDCBackend()

    def _auth(self, claims=CLAIMS):
        request = self.factory.get("/admin/oauth/entra/callback/")
        return self.backend.authenticate(request, claims=claims)

    def test_no_claims_returns_none(self):
        # So password logins fall through to ModelBackend untouched.
        self.assertIsNone(self._auth(claims=None))

    @override_settings(ENTRA_AUTO_CREATE_USERS=True, ENTRA_AUTO_GRANT_IS_STAFF=False,
                       ENTRA_DEFAULT_TEAM_NAME="", ENTRA_ALLOWED_DOMAINS=[])
    def test_auto_create_user_has_no_access(self):
        user = self._auth()
        self.assertIsNotNone(user)
        self.assertEqual(user.email, "alice@example.com")
        self.assertEqual(user.username, "alice@example.com")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.teams.exists())
        self.assertEqual(user.first_name, "Alice")
        self.assertEqual(user.last_name, "Smith")

    @override_settings(ENTRA_AUTO_CREATE_USERS=False, ENTRA_ALLOWED_DOMAINS=[])
    def test_no_auto_create_rejects_unknown_user(self):
        self.assertIsNone(self._auth())
        self.assertFalse(User.objects.exists())

    @override_settings(ENTRA_AUTO_CREATE_USERS=True, ENTRA_ALLOWED_DOMAINS=[])
    def test_matches_existing_user_by_email_no_duplicate(self):
        existing = User.objects.create_user(
            username="alice", email="alice@example.com", password="pw", is_staff=True
        )
        user = self._auth()
        self.assertEqual(user.pk, existing.pk)
        self.assertEqual(User.objects.count(), 1)
        self.assertTrue(user.is_staff)  # existing staff flag preserved

    @override_settings(ENTRA_AUTO_CREATE_USERS=True, ENTRA_ALLOWED_DOMAINS=["other.com"])
    def test_domain_allow_list_rejects(self):
        self.assertIsNone(self._auth())
        self.assertFalse(User.objects.exists())

    @override_settings(ENTRA_AUTO_CREATE_USERS=True, ENTRA_AUTO_GRANT_IS_STAFF=True,
                       ENTRA_DEFAULT_TEAM_NAME="Default", ENTRA_ALLOWED_DOMAINS=[])
    def test_provisioning_hooks_when_enabled_and_idempotent(self):
        user = self._auth()
        self.assertTrue(user.is_staff)
        self.assertTrue(user.teams.filter(name="Default").exists())
        # Second login must not error on the unique_together constraint.
        user2 = self._auth()
        self.assertEqual(user2.pk, user.pk)
        self.assertEqual(TeamMembership.objects.filter(user=user).count(), 1)
        self.assertEqual(Team.objects.filter(name="Default").count(), 1)


@override_settings(ENTRA_AUTH_ENABLED=True, ENTRA_AUTO_CREATE_USERS=True,
                   ENTRA_ALLOWED_DOMAINS=[], ENTRA_REDIRECT_URI="http://testserver/cb")
class EntraViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    @patch("advertising.entra_views._build_msal_app")
    def test_login_stores_flow_and_redirects(self, build_app):
        build_app.return_value.initiate_auth_code_flow.return_value = {
            "auth_uri": "https://login.microsoftonline.com/authorize?x=1",
            "state": "abc",
        }
        resp = self.client.get("/admin/oauth/entra/login/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login.microsoftonline.com", resp["Location"])
        self.assertIn("entra_flow", self.client.session)

    @patch("advertising.entra_views._build_msal_app")
    def test_callback_logs_user_in(self, build_app):
        # A configured (staff) account signs in and is taken into the admin.
        User.objects.create_user(
            username="alice@example.com", email="alice@example.com", is_staff=True
        )
        session = self.client.session
        session["entra_flow"] = {"state": "abc"}
        session.save()
        build_app.return_value.acquire_token_by_auth_code_flow.return_value = {
            "id_token_claims": CLAIMS,
        }
        resp = self.client.get("/admin/oauth/entra/callback/?code=xyz&state=abc")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/admin/")
        self.assertIn("_auth_user_id", self.client.session)
        self.assertTrue(User.objects.filter(email="alice@example.com").exists())

    @patch("advertising.entra_views._build_msal_app")
    def test_callback_unconfigured_user_shows_pending_page(self, build_app):
        # No pre-existing account and no auto-granted staff: the user is created
        # but has no access, so they see the "pending configuration" page rather
        # than being bounced to the login screen.
        session = self.client.session
        session["entra_flow"] = {"state": "abc"}
        session.save()
        build_app.return_value.acquire_token_by_auth_code_flow.return_value = {
            "id_token_claims": CLAIMS,
        }
        resp = self.client.get("/admin/oauth/entra/callback/?code=xyz&state=abc")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "successfully signed in")
        self.assertContains(resp, "Alice Smith")
        # Deliberately not logged in, and the stub still exists for an admin.
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(User.objects.filter(email="alice@example.com").exists())

    @patch("advertising.entra_views._build_msal_app")
    def test_callback_error_redirects_to_login_without_auth(self, build_app):
        session = self.client.session
        session["entra_flow"] = {"state": "abc"}
        session.save()
        build_app.return_value.acquire_token_by_auth_code_flow.return_value = {
            "error": "invalid_grant", "error_description": "bad code",
        }
        resp = self.client.get("/admin/oauth/entra/callback/?code=xyz&state=abc")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("admin:login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_callback_without_session_flow_redirects(self):
        resp = self.client.get("/admin/oauth/entra/callback/?code=xyz&state=abc")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("admin:login"))
        self.assertNotIn("_auth_user_id", self.client.session)


class EntraMiddlewareIntegrationTests(TestCase):
    """A freshly auto-provisioned (non-staff, teamless) user has no access."""

    def setUp(self):
        self.client = Client()

    def test_non_staff_user_denied_then_allowed_after_promotion(self):
        user = User.objects.create_user(username="bob@example.com", email="bob@example.com")
        user.set_unusable_password()
        user.save()
        self.client.force_login(user)
        # Non-staff: IpAccessControlMiddleware redirects HTML GETs to login.
        resp = self.client.get("/admin/", HTTP_ACCEPT="text/html")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/", resp["Location"])

        # Promote: staff + a team -> admin index loads.
        user.is_staff = True
        user.save()
        team = Team.objects.create(name="Team A")
        TeamMembership.objects.create(user=user, team=team)
        resp = self.client.get("/admin/")
        self.assertEqual(resp.status_code, 200)


@override_settings(ENTRA_REDIRECT_URI="http://testserver/cb")
class EntraLoginTemplateTests(TestCase):
    def setUp(self):
        self.client = Client()

    @override_settings(ENTRA_AUTH_ENABLED=True)
    def test_button_present_and_form_collapsed_when_enabled(self):
        resp = self.client.get(reverse("admin:login"))
        self.assertContains(resp, "/admin/oauth/entra/login/")
        self.assertContains(resp, "Sign in with Microsoft")
        # Password form is collapsed behind the toggle.
        self.assertContains(resp, "Sign in with a password instead")
        self.assertContains(resp, 'id="login-form" class="hidden"')

    @override_settings(ENTRA_AUTH_ENABLED=False)
    def test_button_absent_and_form_visible_when_disabled(self):
        resp = self.client.get(reverse("admin:login"))
        self.assertNotContains(resp, "/admin/oauth/entra/login/")
        self.assertNotContains(resp, "Sign in with a password instead")
        # Password form shown normally (not collapsed).
        self.assertNotContains(resp, 'id="login-form" class="hidden"')

    def test_return_to_site_link_removed(self):
        resp = self.client.get(reverse("admin:login"))
        self.assertNotContains(resp, "Return to site")


class PreprovisionUserAdminTests(TestCase):
    """The streamlined 'add user' form pre-provisions Entra/SSO accounts."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username="root", email="root@example.com", password="rootpw"
        )
        self.client.force_login(self.admin)
        self.team = Team.objects.create(name="Marketing")
        self.add_url = reverse("admin:auth_user_add")

    def _post(self, **overrides):
        data = {
            "email": "New.User@example.com",
            "first_name": "New",
            "last_name": "User",
            "password1": "",
            "password2": "",
        }
        data.update(overrides)
        return self.client.post(self.add_url, data)

    def test_add_sso_user_without_password(self):
        resp = self._post(is_staff="on", teams=[self.team.pk])
        self.assertEqual(resp.status_code, 302)  # created -> redirect to change page
        user = User.objects.get(email="new.user@example.com")
        self.assertEqual(user.username, "new.user@example.com")  # derived from email
        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.is_staff)
        self.assertTrue(user.teams.filter(pk=self.team.pk).exists())

    def test_add_user_links_to_entra_login_no_duplicate(self):
        # The crux: a stub created here is matched (not duplicated) on first SSO
        # login, even when the incoming UPN differs only in case.
        self._post(is_staff="on", teams=[self.team.pk])
        stub = User.objects.get(email="new.user@example.com")
        request = RequestFactory().get("/admin/oauth/entra/callback/")
        with override_settings(ENTRA_AUTO_CREATE_USERS=True, ENTRA_ALLOWED_DOMAINS=[]):
            user = EntraOIDCBackend().authenticate(
                request,
                claims={"preferred_username": "NEW.USER@example.com", "name": "New User"},
            )
        self.assertEqual(user.pk, stub.pk)
        self.assertEqual(User.objects.filter(email="new.user@example.com").count(), 1)

    def test_add_user_with_password_is_usable(self):
        resp = self._post(password1="Str0ng!Passw0rd", password2="Str0ng!Passw0rd")
        self.assertEqual(resp.status_code, 302)
        user = User.objects.get(email="new.user@example.com")
        self.assertTrue(user.has_usable_password())

    def test_duplicate_email_rejected(self):
        User.objects.create_user(username="existing", email="new.user@example.com")
        resp = self._post()
        self.assertEqual(resp.status_code, 200)  # re-render with errors, no redirect
        self.assertContains(resp, "already exists")
        self.assertEqual(User.objects.filter(email="new.user@example.com").count(), 1)
