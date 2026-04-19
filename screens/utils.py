import socket

from advertising.settings import USE_FIRST_FORWARDED_FOR_IP, USE_LAST_FORWARDED_FOR_IP


def get_client_ip(request):
    if USE_LAST_FORWARDED_FOR_IP:
        return request.META.get('HTTP_X_FORWARDED_FOR').split(",")[-1].strip()
    if USE_FIRST_FORWARDED_FOR_IP:
        return request.META.get('HTTP_X_FORWARDED_FOR').split(",")[0].strip()
    return request.META.get('REMOTE_ADDR')


def get_client_hostname(ip):
    try:
        return socket.gethostbyaddr(ip)[0] or "Unknown Device"
    except socket.error:
        return "Unknown Device"
