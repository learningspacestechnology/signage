from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone


class AccountLifecycle(models.Model):
    """Bookkeeping for the inactivity rule in `screens.account_inactivity`.

    One row per user, created only once there is something to record. Not
    registered in the admin: it is read through the Users list, and nobody
    should be editing it by hand.

    It also carries the `exempt_from_inactivity_removal` permission, handed
    out through the "Exempt from inactivity removal" group (migration 0040).
    """

    user = models.OneToOneField(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="lifecycle",
    )
    # Activity that `last_login` does not capture: an admin reactivating the
    # account, or the nightly job finding a live session (sessions are pushed
    # back whenever they change, so a daily user may not log in for months).
    last_seen = models.DateTimeField(null=True, blank=True)
    # When the nightly job marked the account inactive. Deletion is counted
    # from here; cleared when the account is reactivated.
    deactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # No add/change/delete/view: there is no admin for these rows, so the
        # stock permissions would only clutter the permission picker.
        default_permissions = ()
        permissions = [
            ("exempt_from_inactivity_removal", "Exempt from removal after inactivity"),
        ]

    def __str__(self):
        return f"{self.user} · lifecycle"


@receiver(pre_save, sender="auth.User")
def note_reactivation(sender, instance, update_fields=None, **kwargs):
    """Restart the inactivity clock when an account is reactivated.

    Otherwise ticking Active on an account the job deactivated would be undone
    the next night, since its `last_login` is still a year old.
    """
    if instance.pk is None or not instance.is_active:
        return
    # A login saves with update_fields=["last_login"]: no extra query for it.
    if update_fields is not None and "is_active" not in update_fields:
        return
    was_active = (sender.objects.filter(pk=instance.pk)
                  .values_list("is_active", flat=True).first())
    if was_active is False:
        AccountLifecycle.objects.update_or_create(
            user_id=instance.pk,
            defaults={"last_seen": timezone.now(), "deactivated_at": None},
        )
