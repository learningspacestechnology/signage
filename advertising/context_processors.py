from django.conf import settings

from advertising.password_auth import password_login_enabled


def entra_flags(request):
    """Expose sign-in availability to templates (e.g. the login page)."""
    return {
        "entra_auth_enabled": getattr(settings, "ENTRA_AUTH_ENABLED", False),
        "password_login_enabled": password_login_enabled(),
    }
