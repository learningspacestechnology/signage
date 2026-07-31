"""Admin-mounted URLs for the help documentation.

Composed into ``admin.site.get_urls`` by ``advertising/admin.py``, the same way
``get_o365_admin_urls()`` is, so the names resolve as ``admin:help_index`` etc.
and every view is behind ``admin_view`` (staff-only).
"""
from django.contrib import admin
from django.urls import path

from helpdocs import views


def get_help_admin_urls():
    wrap = admin.site.admin_view
    return [
        path('help/', wrap(views.help_index), name='help_index'),
        path('help/<slug:audience>/', wrap(views.help_index), name='help_section'),
        path(
            'help/<slug:audience>/<slug:slug>/',
            wrap(views.help_page),
            name='help_page',
        ),
    ]
