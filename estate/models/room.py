from django.db import models

from .building import Building


class Room(models.Model):
    """A room as the datastore's /v1/signage/rooms/ feed describes it.

    Read-only mirror: written only by `estate.sync`, never by the admin.
    """

    lsd_id = models.CharField(
        max_length=255, unique=True, editable=False,
        verbose_name="Datastore id",
        help_text="The datastore's stable key for this room.")
    name = models.CharField(max_length=255)
    building = models.ForeignKey(
        Building, on_delete=models.PROTECT, related_name='rooms')

    # --- what kind of space it is -----------------------------------------
    room_status = models.CharField(
        max_length=100, blank=True, default='', db_index=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    # The datastore derives this from the room's usage start and end dates,
    # which it does not publish: true when today falls inside them, with a
    # missing date counting as open-ended. It changes at midnight with no
    # upstream edit, so it is only as fresh as the last sync. Displayed and
    # filterable, never used to hide a room — a room that opens next month may
    # rightly get its screen now.
    active = models.BooleanField(
        default=True, db_index=True, verbose_name="open today",
        help_text="Open today, by the datastore's start and end dates for "
                  "this room. Screens in an inactive room are flagged.")

    # --- where it is -------------------------------------------------------
    # The feed's pattern allows at most three integer digits and six decimals,
    # which is exactly max_digits=9, decimal_places=6.
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True)
    address = models.CharField(max_length=500, blank=True, default='')
    # Estates' own building code. Per room rather than on Building because the
    # two do not nest: Estates sees some buildings we name in parts as one code
    # (0228 spans "40 George Sq" and its Lower Hub) and gives one building we
    # name once several (IGMM), so a single column on Building would be lossy.
    # Blank for guest and leased buildings, which Estates does not own.
    building_code = models.CharField(
        max_length=20, blank=True, default='', db_index=True,
        verbose_name="Estates building code",
        help_text="Estates' code for the building this room is in. Not unique "
                  "to one building, and blank where Estates does not own it.")
    # Kept as text, not a key: it is the public grouping ("Central",
    # "Lauriston", "New College") rather than campus_lst, is blank on nearly
    # half the rooms, and can differ between rooms of one building. Named so
    # as not to collide with the `campus` property below, which is the one to
    # use.
    public_campus = models.CharField(
        max_length=200, blank=True, default='',
        help_text="The datastore's public campus grouping, as sent for this "
                  "room. Informational; the campus is the building's.")

    # --- who looks after it ------------------------------------------------
    support_type = models.CharField(
        max_length=100, blank=True, default='', db_index=True)
    service_provider = models.CharField(
        max_length=200, blank=True, default='', db_index=True)
    voip_number = models.BigIntegerField(
        null=True, blank=True, verbose_name="VoIP number")

    # --- other systems' keys ----------------------------------------------
    optime_index = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Optime index",
        help_text="The timetabling system's id for this room, where it has one.")

    missing_from_source = models.BooleanField(
        default=False,
        help_text="Set automatically when the datastore stops returning this "
                  "room. Kept rather than deleted because something here still "
                  "points at it.")
    last_seen_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ['building__name', 'name']
        verbose_name = 'estate room'
        verbose_name_plural = 'estate rooms'
        indexes = [models.Index(fields=['building', 'name'])]

    def __str__(self):
        return f"{self.building.name} — {self.name}"

    @property
    def campus(self):
        """The campus, through the building.

        Not a stored column even though the feed puts ``campus_lst`` on every
        room row: two sources of truth for "which campus" is exactly how a
        signage system ends up placing a screen on the wrong one. The sync
        counts disagreements instead of storing them. (``public_campus`` is a
        different, coarser grouping, stored as text only.)
        """
        return self.building.campus

    @property
    def has_support_contact(self):
        return bool(self.service_provider or self.voip_number)
