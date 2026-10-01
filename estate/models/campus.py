from django.db import models


class Campus(models.Model):
    """A campus, as the Learning Spaces Datastore names it.

    Read-only mirror: written only by `estate.sync`, never by the admin.

    LSD publishes no campus endpoint, so campuses are derived from the room
    list. `campus_lst` — the internal name the Learning Spaces team actually
    uses — is the identity.

    `campus_name_short` is stored as `code` but is deliberately *not* the key:
    it arrives with case variants ("cw" and "CW") and blank on some rows, and
    the older feed used one value ("KB") for two different campuses. It is an
    attribute resolved by majority, not an identifier.

    Nor is the feed's `campus` field: that is a coarser public grouping
    ("Central" spans three of these), blank on nearly half the rooms. It is
    kept as `Room.public_campus`, as text.
    """

    name = models.CharField(
        max_length=200, unique=True,
        help_text="The datastore's campus_lst — the internal campus name.")
    code = models.CharField(
        max_length=20, blank=True, default='', db_index=True,
        verbose_name="Short code",
        help_text="The datastore's campus_name_short. Informational; not used "
                  "to identify the campus.")
    missing_from_source = models.BooleanField(
        default=False,
        help_text="Set automatically when the datastore stops returning any "
                  "room on this campus.")
    last_seen_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ['name']
        verbose_name = 'campus'
        # Django would otherwise pluralise this as "campuss".
        verbose_name_plural = 'campuses'

    def __str__(self):
        return f"{self.name} ({self.code})" if self.code else self.name
