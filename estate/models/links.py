"""Links from the room_schedules display records to the estate directory.

The link lives here rather than as a `ForeignKey('estate.Room', ...)` column on
the room_schedules models on purpose. `room_schedules` is a git submodule shared
with other consumers; an FK into `estate` would make this app a hard requirement
of it, and any checkout without `estate` installed would fail Django's system
checks at startup with fields.E300 — not just lose the feature. Owning the link
from this side keeps the submodule usable by everyone and the change in one repo.
"""

from django.conf import settings
from django.db import models


class BuildingLink(models.Model):
    """Ties a room_schedules display building to its estate building."""

    display_building = models.OneToOneField(
        'room_schedules.Building', on_delete=models.CASCADE,
        related_name='estate_link',
        verbose_name="Display building")
    # A plain FK, not OneToOne: one estate building may legitimately back
    # several display buildings, because a display building is a *display
    # config* unit and a large building is often split into two of them.
    estate_building = models.ForeignKey(
        'estate.Building', on_delete=models.PROTECT,
        related_name='display_links')

    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['estate_building__name']
        verbose_name = 'building link'

    def __str__(self):
        return f"{self.display_building} → {self.estate_building}"


class RoomLink(models.Model):
    """Ties a room_schedules display room to its estate room."""

    display_room = models.OneToOneField(
        'room_schedules.Room', on_delete=models.CASCADE,
        related_name='estate_link',
        verbose_name="Display room")
    # OneToOne on both sides here, unlike BuildingLink: two display rooms
    # pointing at one estate room is a data-entry mistake worth catching at the
    # database rather than discovering in a room display later.
    estate_room = models.OneToOneField(
        'estate.Room', on_delete=models.PROTECT,
        related_name='display_link')

    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['estate_room__name']
        verbose_name = 'room link'

    def __str__(self):
        return f"{self.display_room} → {self.estate_room}"
