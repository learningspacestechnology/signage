"""HTTP views for the Microsoft Entra ID authorization-code sign-in flow.

`entra_login` kicks off the flow; Microsoft redirects back to
`entra_callback`, which exchanges the code, validates the ID token (via MSAL)
and logs the user in through `advertising.entra_auth.EntraOIDCBackend`.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from advertising.entra_auth import _build_msal_app

_FLOW_SESSION_KEY = "entra_flow"
_NEXT_SESSION_KEY = "entra_next"
_BACKEND = "advertising.entra_auth.EntraOIDCBackend"


def _safe_next(request, candidate):
    """Return `candidate` if it's a safe local redirect, else None."""
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return None


def entra_login(request):
    """Begin the auth-code flow and redirect the user to Microsoft."""
    # Pass scopes=[] — MSAL injects the reserved openid/profile/offline_access
    # itself and raises if they are passed explicitly.
    flow = _build_msal_app().initiate_auth_code_flow(
        scopes=[],
        redirect_uri=settings.ENTRA_REDIRECT_URI,
    )
    request.session[_FLOW_SESSION_KEY] = flow  # holds state, PKCE verifier, nonce

    nxt = _safe_next(request, request.GET.get("next"))
    if nxt:
        request.session[_NEXT_SESSION_KEY] = nxt

    return redirect(flow["auth_uri"])


def entra_callback(request):
    """Handle Microsoft's redirect: exchange code, validate, log in."""
    login_url = reverse("admin:login")

    flow = request.session.pop(_FLOW_SESSION_KEY, None)
    if not flow:
        return redirect(login_url)

    result = _build_msal_app().acquire_token_by_auth_code_flow(
        flow, request.GET.dict()
    )
    if "id_token_claims" not in result:
        messages.error(
            request, result.get("error_description", "Microsoft sign-in failed.")
        )
        return redirect(login_url)

    user = authenticate(request, claims=result["id_token_claims"])
    if user is None:
        messages.error(
            request, "Your Microsoft account is not permitted to sign in."
        )
        return redirect(login_url)

    login(request, user, backend=_BACKEND)

    nxt = _safe_next(request, request.session.pop(_NEXT_SESSION_KEY, None))
    return redirect(nxt or "/admin/")
