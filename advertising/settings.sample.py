"""Template for `advertising/settings.py` — this checkout's local settings.

    cp advertising/settings.sample.py advertising/settings.py

`advertising/settings.py` is **not tracked in git**: it holds whatever this
machine needs, including credentials. Only this template is committed, so a real
secret can never be published by a routine `git add`.

Layer 2 of the three-layer settings model (see CLAUDE.md, "Settings"):

1. `advertising/base_settings.py` — plain defaults, committed. No env reads.
2. `advertising/settings.py` — **you are here**: hardcoded local overrides.
3. Production — the deploy repo's `docker/advertising/settings.py`, copied over
   this file at image build, reading everything from `.env`.

The values below are placeholders. Everything except the O365 block is optional;
delete what you don't need.
"""
from .base_settings import *  # noqa: F401,F403

# ---------------------------------------------------------------------------
# Required — the app will not start without these
# ---------------------------------------------------------------------------
# `room_schedules/settings.py` raises at import time unless all three are set to
# a non-empty value, which means a missing one is a total startup failure rather
# than "room displays don't work". The placeholders below satisfy that guard and
# authenticate against nothing; replace them only if you are working on the room
# integration and have real credentials to use.
O365_CLIENT_ID = 'local-placeholder-client-id'
O365_TENANT_ID = 'local-placeholder-tenant-id'
O365_CLIENT_SECRET = 'local-placeholder-client-secret'

# Optional: authenticate as a service account with Exchange read access to the
# room mailboxes, instead of as the application itself.
# O365_DELEGATED_USERNAME = ''
# O365_DELEGATED_PASSWORD = ''

# ---------------------------------------------------------------------------
# Local development conveniences
# ---------------------------------------------------------------------------
ALLOWED_HOSTS = ['*']

# Run Celery tasks inline instead of needing a worker and Redis.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# No reverse proxy in front of runserver, so take the client IP as-is.
USE_FIRST_FORWARDED_FOR_IP = False
USE_LAST_FORWARDED_FOR_IP = False

# ---------------------------------------------------------------------------
# Microsoft Entra sign-in
# ---------------------------------------------------------------------------
# Off by default: with it on, the login page offers a "Sign in with Microsoft"
# button that cannot work without a real app registration. Leave it off and use
# a password account locally.
ENTRA_AUTH_ENABLED = False
# ENTRA_CLIENT_ID = ''
# ENTRA_TENANT_ID = ''
# ENTRA_CLIENT_SECRET = ''
# ENTRA_AUTHORITY = f'https://login.microsoftonline.com/{ENTRA_TENANT_ID}'
# ENTRA_REDIRECT_URI = 'http://localhost:8000/admin/oauth/entra/callback/'
# ENTRA_ALLOWED_DOMAINS = ''

# ---------------------------------------------------------------------------
# Behaviour you may want to vary while developing
# ---------------------------------------------------------------------------
# Upload limits — a hard per-axis reject, not a downscale, so orientation
# matters: the defaults below admit landscape 4K and turn away portrait 4K.
# Safe to change freely; they are read through `django.conf.settings` at request
# time and no longer reach migration state.
# MAX_IMG_WIDTH = 3840
# MAX_IMG_HEIGHT = 2160

# Shown in the header, on the login page and on the logout page.
# ADMIN_SITE_NAME = 'Display Screen Admin'

# Shown on a display whose IP is not registered.
# UNCONFIGURED_SCREEN_MESSAGE = 'This screen is not configured.'

# Set False to let any client load the screen and room-display URLs.
# IP_ACCESS_CONTROL_ENABLED = True

# Create a Screen automatically for any unrecognised IP. Convenient during a
# bulk rollout, noisy the rest of the time.
# AUTO_MAKE_SCREENS_FOR_NEW_IPS = False
