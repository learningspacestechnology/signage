import os

from django.conf import settings
from django.http import Http404, HttpResponse


def serve_media(request, path):
    full = os.path.realpath(os.path.join(settings.MEDIA_ROOT, path))
    media_root = os.path.realpath(settings.MEDIA_ROOT)
    if os.path.commonpath([full, media_root]) != media_root:
        raise Http404
    if not os.path.isfile(full):
        raise Http404
    response = HttpResponse()
    response['X-Accel-Redirect'] = '/protected-media/' + path
    response['Content-Type'] = ''
    return response
