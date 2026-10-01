"""Admin-site URLs for the estate app.

Lives in urls.py rather than admin.py, and is composed into
`advertising.admin._patched_admin_get_urls` alongside `get_help_admin_urls()`
and `get_o365_admin_urls()`, so the names resolve as `admin:estate_*` and the
URLs sit under /admin/estate/ rather than under one ModelAdmin.
"""

from django.contrib import admin
from django.urls import path

from estate import views
from estate.picker import RoomPickerJsonView


def get_estate_admin_urls():
    wrap = admin.site.admin_view
    return [
        # "estate/building-screens/<id>/" rather than
        # "estate/building/<id>/screens/": ModelAdmin.get_urls ends with a
        # catch-all `<path:object_id>/` legacy redirect, and the latter shape
        # would collide with it the day someone reorders the URL list — failing
        # as a silent redirect to the change page rather than an error.
        path('estate/building-screens/<int:building_id>/',
             wrap(views.building_screens_view),
             name='estate_building_screens'),
        path('estate/link-rooms/',
             wrap(views.room_links_view),
             name='estate_room_links'),
        path('estate/sync-now/',
             wrap(views.estate_sync_now_view),
             name='estate_sync_now'),
        path('estate/room-picker/',
             wrap(RoomPickerJsonView.as_view(admin_site=admin.site)),
             name='estate_room_picker'),
    ]
