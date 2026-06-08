from datetime import datetime
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse

from screens.models import Source


def flatten(t):
    return [item for sublist in t for item in sublist]


class Playlist(models.Model):
    name = models.TextField()
    description = models.TextField(blank=True)
    interspersed_source = models.ForeignKey(Source, null=True, default=None, on_delete=models.SET_NULL, blank=True,
                                            verbose_name="Interspersed Content",
                                            help_text="A single piece of content shown between each regular entry "
                                                      "(e.g. a logo or ad between every slide). It is not part of the "
                                                      "normal rotation. Leave blank for none.")
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

    def parent_sources(self, block_list):
        block_list.append(self.id)
        return flatten(map(lambda x: x.get_sources(block_list), self.parents.exclude(id__in=block_list)))

    def get_sources(self, block_list=None):
        if block_list is None:
            block_list = []
        now = datetime.now()
        return list(self.playlistentry_set.select_related("source")
                    .exclude(source_id=self.interspersed_source_id)
                    .filter(Q(source__valid_from__lte=now) | Q(source__valid_from__isnull=True))
                    .filter(Q(source__expires_at__gte=now) | Q(source__expires_at__isnull=True))
                    .order_by('number')) + self.parent_sources(block_list)

    def get_resolved_sources(self, block_list=None):
        entries = self.get_sources(block_list)
        if len(entries) == 1:
            entries[0].duration = 3600
        else:
            for entry in entries:
                if entry.duration is None:
                    entry.duration = self.default_duration
        return entries

    def meta_times_touch(self, block_list=None):
        if block_list is None:
            block_list = []
        block_list.append(self.id)
        self.last_updated = datetime.now()
        self.save()
        for child in self.children.exclude(id__in=block_list):
            child.meta_times_touch(block_list)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('screens/playlist_view', args=[str(self.id)])
