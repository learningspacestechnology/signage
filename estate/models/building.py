from django.db import models

from .campus import Campus


class Building(models.Model):
    """A building, derived from the room list.

    The datastore has no /buildings/ endpoint, so buildings are the distinct
    (campus_lst, building) pairs across the whole room feed. The feed's
    `building_code` is Estates' own and does not nest with our building names
    — it is stored on each Room instead; `estates_codes` rolls it up here.
    Read-only mirror, written only by `estate.sync`.
    """

    #: The derived natural key, "<campus>|<building>" normalised. See
    #: `estate.sync.building_key`.
    #:
    #: The campus has to be in it: one building name in the live data ("Medical
    #: School") appears on two different campuses, and they are different
    #: buildings. Name alone would silently merge them.
    key = models.CharField(max_length=255, unique=True, editable=False)
    name = models.CharField(max_length=255)
    campus = models.ForeignKey(
        Campus, on_delete=models.PROTECT, related_name='buildings')

    missing_from_source = models.BooleanField(
        default=False,
        help_text="Set automatically when the datastore stops returning any "
                  "room in this building.")
    last_seen_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ['campus__name', 'name']
        verbose_name = 'estate building'
        verbose_name_plural = 'estate buildings'
        indexes = [models.Index(fields=['campus', 'name'])]

    def __str__(self):
        return self.name

    @property
    def estates_codes(self):
        """The distinct Estates building codes this building's rooms carry.

        Usually one; several where Estates splits what we call one building
        (IGMM), none for a guest or leased building. One query — fine on a
        detail page, not for a changelist column.
        """
        # order_by() clears Room.Meta.ordering, whose columns Django would
        # otherwise add to the SELECT DISTINCT — one row per room, not per code.
        return list(
            self.rooms.exclude(building_code='')
            .order_by('building_code')
            .values_list('building_code', flat=True).distinct())
