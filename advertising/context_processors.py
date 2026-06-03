from django.conf import settings


def entra_flags(request):
    """Expose Entra sign-in availability to templates (e.g. the login page)."""
    return {
        "entra_auth_enabled": getattr(settings, "ENTRA_AUTH_ENABLED", False),
    }
