from django.db import models
from django.db.models.signals import pre_delete, pre_save
from django.dispatch import receiver

from screens.models import Playlist


class PlaylistRelation(models.Model):
    super_list = models.ForeignKey(Playlist, on_delete=models.PROTECT, related_name="children_list", verbose_name="Parent",
                                   help_text="The parent playlist to inherit content from.") #limit_choices_to
    inheriting_list = models.ForeignKey(Playlist, on_delete=models.CASCADE, related_name="parents_list",
                                        help_text="The child playlist that receives the parent's content.")

    def __str__(self):
        return f"{self.inheriting_list} inherits from {self.super_list}"


@receiver(pre_delete, sender=PlaylistRelation)
@receiver(pre_save, sender=PlaylistRelation)
def relation_changed(sender, instance=None, raw=False, **kwargs):
    """Republish the child whenever it gains or loses a parent.

    pre_delete matters as much as pre_save, and was the half that was missing.
    Adding a parent bumped the child's last_updated and so reached devices;
    *removing* one did not. The child's content shrinks by everything it was
    inheriting while its timestamp stays put, so every screen on that playlist
    carries on showing the parent's items for up to an hour — until the player's
    page-level <meta http-equiv="refresh"> fires.

    That is the wrong way round: the whole point of unticking a parent is to
    stop something being displayed, which is exactly the case that did not
    propagate.

    Two details make stacking the decorator sufficient. The row still exists at
    pre_delete, so inheriting_list resolves and can be touched. And connecting
    any pre_delete receiver disqualifies the model from Django's fast-path bulk
    delete, so the collector fetches each object and fires signals individually
    — meaning parents.remove() and the admin inline's Delete box both reach it.
    """
    if instance is None or raw:
        return

    instance.inheriting_list.meta_times_touch()
