from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden, HttpResponse
from django.template.loader import render_to_string

from screens.utils import get_client_ip


ALLOW_PREFIXES = ('/admin/', '/static/')


class _AllTeamsSentinel:
    """Marker used in place of a Team to mean 'show every team's content'."""

    def __repr__(self):
        return "ALL_TEAMS"

    def __bool__(self):
        return True


ALL_TEAMS = _AllTeamsSentinel()


# Paths the active-team middleware should leave alone even though they live
# under /admin/. The login/logout pages run before a user is authenticated,
# and the set-active-team endpoint writes to the session itself.
_ACTIVE_TEAM_BYPASS_PREFIXES = (
    '/admin/login/',
    '/admin/logout/',
    '/admin/password_change/',
    '/admin/set-active-team/',
)

# Endpoints whose views handle unregistered IPs themselves — either by
# auto-creating a Screen (when AUTO_MAKE_SCREENS_FOR_NEW_IPS=True) or by
# rendering the "unconfigured screen" page/JSON. These must always be
# reachable so a fresh device can announce itself and the operator can read
# its IP off the unconfigured page. Only the root entry points are listed
# here; sub-paths that require an explicit ID remain gated.
SCREEN_DISCOVERY_PATHS = (
    '/screen/', '/screen',
    '/api/screen/', '/api/screen',
    '/meta', '/api/meta',
    '/api/unconfigured',
    '/event_schedules/', '/event_schedules',
)


class IpAccessControlMiddleware:
    """
    Restrict the public URLs (screens, playlists, room schedules, media) to
    either an authenticated admin user OR a request whose client IP matches a
    registered Screen / IpAddress (room / building / room group).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, 'IP_ACCESS_CONTROL_ENABLED', True):
            return self.get_response(request)

        path = request.path
        if path == '/' or any(path.startswith(p) for p in ALLOW_PREFIXES):
            return self.get_response(request)

        if request.user.is_authenticated and request.user.is_staff:
            return self.get_response(request)

        ip = get_client_ip(request)

        if settings.DEBUG and ip in ('127.0.0.1', '::1'):
            return self.get_response(request)

        if ip and self._ip_is_registered(ip):
            return self.get_response(request)

        if path in SCREEN_DISCOVERY_PATHS:
            return self.get_response(request)

        return self._deny(request)

    @staticmethod
    def _ip_is_registered(ip):
        from screens.models import Screen
        if Screen.objects.filter(ip=ip).exists():
            return True
        if 'room_schedules' in settings.INSTALLED_APPS:
            from room_schedules.models import IpAddress
            if IpAddress.objects.filter(ip_address=ip).exists():
                return True
        return False

    @staticmethod
    def _deny(request):
        wants_html = (
            request.method == 'GET'
            and 'text/html' in request.META.get('HTTP_ACCEPT', '')
        )
        if wants_html:
            return redirect_to_login(request.get_full_path(), '/admin/login/')
        return HttpResponseForbidden('Access denied: IP not registered')


SESSION_KEY = 'active_team_id'
ALL_TEAMS_SESSION_VALUE = 'all'


class ActiveTeamMiddleware:
    """
    Resolve `request.active_team` for admin requests by authenticated staff.

    Reads the active team from session (`ALL_TEAMS` sentinel or a `Team`),
    defaults superusers to ALL_TEAMS and regular users to their first team,
    and blocks regular users with no team memberships from the admin index.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_team = None

        if not request.path.startswith('/admin/'):
            return self.get_response(request)
        if any(request.path.startswith(p) for p in _ACTIVE_TEAM_BYPASS_PREFIXES):
            return self.get_response(request)
        if not (request.user.is_authenticated and request.user.is_staff):
            return self.get_response(request)

        from screens.models import Team

        user_teams_qs = request.user.teams.all().order_by('name')

        if not request.user.is_superuser and not user_teams_qs.exists():
            return self._no_team_response(request)

        stored = request.session.get(SESSION_KEY)
        active = self._resolve_stored(stored, request.user, user_teams_qs, Team)

        if active is None:
            active = ALL_TEAMS if request.user.is_superuser else user_teams_qs.first()
            self._persist(request, active)

        request.active_team = active
        return self.get_response(request)

    @staticmethod
    def _resolve_stored(stored, user, user_teams_qs, Team):
        if stored == ALL_TEAMS_SESSION_VALUE:
            return ALL_TEAMS if user.is_superuser else None
        if isinstance(stored, int):
            if user.is_superuser:
                return Team.objects.filter(pk=stored).first()
            return user_teams_qs.filter(pk=stored).first()
        return None

    @staticmethod
    def _persist(request, active):
        if active is ALL_TEAMS:
            request.session[SESSION_KEY] = ALL_TEAMS_SESSION_VALUE
        else:
            request.session[SESSION_KEY] = active.pk

    @staticmethod
    def _no_team_response(request):
        html = render_to_string(
            'admin/no_team_assigned.html',
            {'user': request.user},
            request=request,
        )
        return HttpResponse(html, status=403)
