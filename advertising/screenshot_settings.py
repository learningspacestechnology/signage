"""Settings for capturing help-documentation screenshots.

Used only by ``manage.py capture_help_screenshots``:

    DJANGO_SETTINGS_MODULE=advertising.screenshot_settings \\
        uv run python manage.py capture_help_screenshots

This deliberately extends ``base_settings`` rather than ``settings``. The dev
settings module holds **real Microsoft credentials** and sets
``CELERY_TASK_ALWAYS_EAGER``, so a task triggered during a capture run would
execute synchronously against the live tenant. Starting from the base defaults
and substituting placeholders makes that impossible.

Everything it writes lives under ``.help-capture/`` (git-ignored) — the
development database and media directory are never touched.
"""
import os

from .base_settings import *  # noqa: F401,F403
from .base_settings import BASE_DIR

CAPTURE_ROOT = os.path.join(BASE_DIR, '.help-capture')

DEBUG = True
ALLOWED_HOSTS = ['*']

# Throwaway database and media, rebuilt from scratch on every capture run.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(CAPTURE_ROOT, 'capture.sqlite3'),
        'OPTIONS': {'timeout': 20},
    }
}
MEDIA_ROOT = os.path.join(CAPTURE_ROOT, 'media')

# Non-empty so room_schedules' import-time guard is satisfied, and useless for
# authenticating against anything. No Graph request is made during a capture —
# the room views read local rows, and no shot triggers a sync or a booking.
O365_CLIENT_ID = 'capture-placeholder-client-id'
O365_CLIENT_SECRET = 'capture-placeholder-client-secret'
O365_TENANT_ID = 'capture-placeholder-tenant-id'
O365_DELEGATED_USERNAME = None
O365_DELEGATED_PASSWORD = None

# Renders the "Sign in with Microsoft" button on the login page without any of
# it being able to reach Microsoft.
ENTRA_AUTH_ENABLED = True
ENTRA_CLIENT_ID = 'capture-placeholder-entra-client-id'
ENTRA_TENANT_ID = 'capture-placeholder-entra-tenant-id'
ENTRA_CLIENT_SECRET = 'capture-placeholder-entra-secret'
ENTRA_AUTHORITY = 'https://login.microsoftonline.example/capture-placeholder'
ENTRA_REDIRECT_URI = 'http://127.0.0.1:8000/admin/oauth/entra/callback/'

# Belt and braces: never run a queued task inline during a capture.
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = False

# The capture browser is not a registered display; let it load screen pages.
IP_ACCESS_CONTROL_ENABLED = False

ADMIN_SITE_NAME = "Signum"
