"""Username/password sign-in, switchable off with `PASSWORD_LOGIN_ENABLED`.

`PasswordBackend` replaces the stock ModelBackend in AUTHENTICATION_BACKENDS.
It must never simply be removed: ModelBackend also answers `has_perm` for
every user however they signed in, and `EntraOIDCBackend` supplies no
permissions of its own, so dropping it would strip every non-superuser of
every permission.
"""

from django.conf import settings
from django.contrib.auth.backends import ModelBackend
from django.core.checks import Warning


def _entra_usable():
    return bool(settings.ENTRA_AUTH_ENABLED and settings.ENTRA_CLIENT_ID)


def password_login_enabled():
    """Whether password sign-in is actually in effect.

    `PASSWORD_LOGIN_ENABLED`, except that it is ignored while Microsoft sign-in
    is off or unconfigured: with both routes closed nobody could sign in at all.
    """
    return settings.PASSWORD_LOGIN_ENABLED or not _entra_usable()


class PasswordBackend(ModelBackend):
    """ModelBackend whose sign-in half obeys `password_login_enabled()`.

    Only `authenticate` and `get_user` are gated. The permission methods are
    inherited untouched, because they serve Entra users too.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not password_login_enabled():
            return None
        return super().authenticate(request, username, password, **kwargs)

    def get_user(self, user_id):
        # Django calls this on the backend recorded in the session, so turning
        # password sign-in off also ends sessions that were started with it.
        if not password_login_enabled():
            return None
        return super().get_user(user_id)


def check_password_login_setting(app_configs, **kwargs):
    """Warn when `PASSWORD_LOGIN_ENABLED = False` is being overridden.

    A Warning rather than an Error: the container runs `migrate` before
    starting, and an Error would stop it and take the screens down too.
    """
    if settings.PASSWORD_LOGIN_ENABLED or _entra_usable():
        return []
    return [
        Warning(
            "PASSWORD_LOGIN_ENABLED is False, but Microsoft sign-in is "
            "disabled or has no ENTRA_CLIENT_ID, so password sign-in stays on.",
            hint="Configure Microsoft sign-in, or set PASSWORD_LOGIN_ENABLED "
                 "back to True.",
            id="advertising.W001",
        )
    ]
