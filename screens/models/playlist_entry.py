from django.db import models
from django.db.models.signals import pre_delete, pre_save
from django.dispatch import receiver
from django.template.loader import get_template

from screens.models.source import Source


class PlaylistEntry(models.Model):
    playlist = models.ForeignKey("Playlist", on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    number = models.IntegerField()
    duration = models.IntegerField(null=True, blank=True,
                                   help_text="seconds to display source for; leave blank to use the playlist's default duration (ignored for videos)")

    class Meta:
        ordering = ['number']

    def __str__(self):
        return ""

    def thumbnail(self):
        if self.source_id is None:
            return ""
        return get_template("screens/source_thumbnail.html").render({"source": self.source})
    thumbnail.short_description = "Preview"


@receiver(pre_delete, sender=PlaylistEntry)
@receiver(pre_save, sender=PlaylistEntry)
def entry_updated(sender, instance=None, raw=False, **kwargs):
    if instance is None or raw:
        return

    instance.playlist.meta_times_touch()
