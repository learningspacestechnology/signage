"""Django's system checks stay clean, so `manage.py` output is readable."""

from django.core.checks import run_checks
from django.test import SimpleTestCase


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
