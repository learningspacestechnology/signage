"""Django's system checks stay clean, so `manage.py` output is readable."""

from django.core.checks import run_checks
from django.test import SimpleTestCase, override_settings


class AutoFieldCheckTests(SimpleTestCase):
    """models.W042 fired once per model — 19 warnings on every `manage.py`
    invocation, burying whatever the command was actually run to show — until
    `DEFAULT_AUTO_FIELD` was set in `advertising/base_settings.py`.

    It must stay `django.db.models.AutoField`, not Django's `BigAutoField`
    default: these tables predate Django 3.2, so `BigAutoField` would ask for an
    `AlterField` on every primary key and every FK referencing them.
    """

    databases = []

    def test_no_auto_created_primary_key_warnings(self):
        offenders = [str(message.obj) for message in run_checks() if message.id == "models.W042"]
        self.assertEqual(offenders, [])


class PasswordLoginCheckTests(SimpleTestCase):
    """`PASSWORD_LOGIN_ENABLED = False` is ignored while Microsoft sign-in is
    unusable, so an operator who set it needs telling. The container runs
    `migrate` at start, which puts this in the log right after the change."""

    databases = []

    def _ids(self):
        return [message.id for message in run_checks()]

    @override_settings(PASSWORD_LOGIN_ENABLED=False, ENTRA_AUTH_ENABLED=True,
                       ENTRA_CLIENT_ID="")
    def test_warns_when_setting_is_overridden(self):
        self.assertIn("advertising.W001", self._ids())

    @override_settings(PASSWORD_LOGIN_ENABLED=False, ENTRA_AUTH_ENABLED=True,
                       ENTRA_CLIENT_ID="x")
    def test_silent_when_entra_is_configured(self):
        self.assertNotIn("advertising.W001", self._ids())

    @override_settings(PASSWORD_LOGIN_ENABLED=True, ENTRA_AUTH_ENABLED=False)
    def test_silent_when_password_login_is_on(self):
        self.assertNotIn("advertising.W001", self._ids())
