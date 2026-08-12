from datetime import datetime
from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone


def flatten(t):
    return [item for sublist in t for item in sublist]


# A playlist holding a single item has nothing to rotate to, so it is held on
# screen rather than being replaced by itself every few seconds.
SINGLE_ITEM_HOLD_SECONDS = 3600


class Playlist(models.Model):
    name = models.TextField()
    description = models.TextField(blank=True)
    interspersed_playlist = models.ForeignKey("self", null=True, default=None, on_delete=models.SET_NULL, blank=True,
                                              related_name="interspersed_into",
                                              verbose_name="Interspersed playlist",
                                              help_text="A playlist whose items are mixed into this one (e.g. a logo "
                                                        "or standing message). Its items are not part of the normal "
                                                        "rotation. Leave blank for none.")
    interspersed_rate = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name="Interspersed rate",
        help_text="How many of this playlist's own items play before one interspersed item. "
                  "1 shows an interspersed item after every entry.",
    )
    last_updated = models.DateTimeField(auto_now=True)
    default_duration = models.PositiveIntegerField(
        default=10,
        help_text="Default display time in seconds for entries that don't set their own duration (ignored for videos).",
    )
    parents = models.ManyToManyField("self", related_name="children", symmetrical=False,
                                     through="PlaylistRelation", through_fields=("inheriting_list", "super_list"),
                                     help_text="Content from these parent playlists is added to this one. "
                                               "This playlist's own entries play first, then inherited content follows.", blank=True)
    teams = models.ManyToManyField("screens.Team", related_name="playlists")

    def clean(self):
        super().clean()
        if self.pk and not self.teams.exists():
            raise ValidationError("Playlist must belong to at least one team.")
        if self.interspersed_playlist_id and self.interspersed_playlist_id == self.pk:
            raise ValidationError(
                {"interspersed_playlist": "A playlist cannot be its own interspersed playlist."})

    def parent_sources(self, block_list):
        block_list.append(self.id)
        return flatten(map(lambda x: x.get_sources(block_list), self.parents.exclude(id__in=block_list)))

    def get_sources(self, block_list=None):
        if block_list is None:
            block_list = []
        now = datetime.now()
        return list(self.playlistentry_set.select_related("source")
                    .filter(Q(source__valid_from__lte=now) | Q(source__valid_from__isnull=True))
                    .filter(Q(source__expires_at__gte=now) | Q(source__expires_at__isnull=True))
                    .order_by('number')) + self.parent_sources(block_list)

    def get_resolved_sources(self, block_list=None, hold_single=True):
        entries = self.get_sources(block_list)
        for entry in entries:
            if entry.duration is None:
                entry.duration = self.default_duration
        if hold_single and len(entries) == 1:
            entries[0].duration = SINGLE_ITEM_HOLD_SECONDS
        return entries

    def get_interspersed_sources(self):
        """Resolve this playlist as an interspersed stream.

        Deliberately starts a fresh block_list: an interspersed playlist that
        also sits in the caller's inheritance chain must expand fully rather
        than be swallowed by the caller's cycle guard.

        Never applies the single-item hold — a one-item logo playlist would
        otherwise sit on screen for an hour instead of flashing past between
        entries.
        """
        return self.get_resolved_sources(block_list=None, hold_single=False)

    def meta_times_touch(self, block_list=None):
        if block_list is None:
            block_list = []
        block_list.append(self.id)
        # last_updated is auto_now, so the save() below stamps it.
        self.save()
        for child in self.children.exclude(id__in=block_list):
            child.meta_times_touch(block_list)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('screens/playlist_view', args=[str(self.id)])


@receiver(pre_delete, sender=Playlist)
def interspersed_referrers_touched(sender, instance=None, **kwargs):
    """Republish anything that was interspersing the playlist being deleted.

    Same failure as the missing pre_delete on PlaylistRelation, reached a
    different way: both interspersed FKs are SET_NULL, which Django applies as a
    bulk UPDATE. That fires no signals and triggers no auto_now, so a referrer
    whose own last_updated is newer than the deleted playlist's keeps the exact
    same aggregate timestamp — and its screens keep playing content that has
    just been deleted outright.

    This is also why the two interspersed FKs use real related_names rather than
    "+": without a reverse accessor there is no way to ask who was pointing at
    this playlist, and so no way to republish them.
    """
    if instance is None:
        return
    for playlist in instance.interspersed_into.all():
        playlist.meta_times_touch()
    # Screen is imported lazily; screens.models.screen imports this module.
    apps.get_model("screens", "Screen").objects \
        .filter(interspersed_playlist=instance) \
        .update(interspersed_last_updated=timezone.now())
