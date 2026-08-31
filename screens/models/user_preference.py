from django.db import models

from screens.accents import DEFAULT_ACCENT


class UserPreference(models.Model):
    """Per-user admin display settings. One row per user, created on first use.

    Deliberately not registered in the admin: it is set through the accent
    picker in the sidebar user menu, and registering it would add a sidebar
    entry and a permissions surface for a personal preference nobody else
    should be editing.
    """

    user = models.OneToOneField(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="admin_preference",
    )
    # No `choices=`: Django records them in migration state, so every palette
    # added or retired would demand an AlterField for a value that is purely
    # cosmetic. `screens.accents.ACCENTS` stays the single source of truth —
    # the view validates writes against it and `accents.resolve()` degrades an
    # unknown slug to the default on read.
    accent = models.CharField(max_length=20, default=DEFAULT_ACCENT)

    def __str__(self):
        return f"{self.user} · {self.accent}"
