"""Microsoft Entra ID (Azure AD) sign-in via a custom MSAL OIDC flow.

This module owns the claim -> Django User mapping and the auto-provisioning
policy. The HTTP auth-code flow lives in `advertising.entra_views`.

MSAL handles the security-sensitive parts (state/PKCE/nonce, ID-token
signature/issuer/audience validation); we only consume the validated claims.
"""

import msal
from django.conf import settings
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import User


def _build_msal_app(cache=None):
    """Return a fresh ConfidentialClientApplication.

    Deliberately NOT a module-level singleton (unlike room_schedules'
    app-only client): each interactive sign-in carries per-user state and
    must not be shared across requests/sessions.
    """
    return msal.ConfidentialClientApplication(
        client_id=settings.ENTRA_CLIENT_ID,
        client_credential=settings.ENTRA_CLIENT_SECRET,
        authority=settings.ENTRA_AUTHORITY,
        token_cache=cache,
    )


class EntraOIDCBackend(BaseBackend):
    """Authenticate a user from validated Entra ID token claims.

    Runs alongside the stock ModelBackend. Returns None whenever `claims`
    is absent so it never interferes with username/password logins.
    """

    def authenticate(self, request, claims=None, **kwargs):
        if not claims:
            return None

        # `preferred_username` is the UPN; fall back to `email`.
        email = (claims.get("preferred_username") or claims.get("email") or "").lower()
        if not email:
            return None

        if settings.ENTRA_ALLOWED_DOMAINS:
            domain = email.rsplit("@", 1)[-1]
            if domain not in settings.ENTRA_ALLOWED_DOMAINS:
                return None

        user = self._match_user(email)
        if user is None:
            if not settings.ENTRA_AUTO_CREATE_USERS:
                return None
            user = User(username=email[:150], email=email)
            user.set_unusable_password()

        self._sync_profile(user, claims)
        self._apply_provisioning(user)
        return user

    def get_user(self, user_id):
        return User.objects.filter(pk=user_id).first()

    @staticmethod
    def _match_user(email):
        """Match an existing account by email, then username.

        Matching by email links an existing password admin to their Entra
        identity rather than creating a duplicate account.
        """
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            user = User.objects.filter(username__iexact=email).first()
        return user

    @staticmethod
    def _sync_profile(user, claims):
        """Best-effort fill of name fields from the `name` claim."""
        name = (claims.get("name") or "").strip()
        if name and not (user.first_name or user.last_name):
            first, _, last = name.partition(" ")
            user.first_name = first[:150]
            user.last_name = last[:150]

    @staticmethod
    def _apply_provisioning(user):
        """Apply the (settings-gated, safe-by-default) provisioning policy.

        Default policy grants no access: is_staff stays False and no Team is
        assigned, so a brand-new SSO user must be promoted by an existing
        admin before they can use the admin.
        """
        if settings.ENTRA_AUTO_GRANT_IS_STAFF:
            user.is_staff = True
        user.save()

        team_name = settings.ENTRA_DEFAULT_TEAM_NAME
        if team_name:
            from screens.models import Team, TeamMembership

            team, _ = Team.objects.get_or_create(name=team_name)
            TeamMembership.objects.get_or_create(user=user, team=team)
