from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden

from screens.utils import get_client_ip


ALLOW_PREFIXES = ('/admin/', '/static/')

# Endpoints whose views handle unregistered IPs themselves (auto-create when
# AUTO_MAKE_SCREENS_FOR_NEW_IPS=True, otherwise render the "unconfigured screen"
# page/JSON). These must always be reachable so a fresh device can announce
# itself and the operator can read its IP off the unconfigured page.
SCREEN_DISCOVERY_PATHS = (
    '/screen/', '/screen',
    '/api/screen/', '/api/screen',
    '/meta', '/api/meta',
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
