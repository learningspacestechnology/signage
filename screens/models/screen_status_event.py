from django.db import models

from screens.models.screen import Screen, ScreenStatus, StatusReason


class ScreenStatusEvent(models.Model):
    """One row per *change* in a screen's status.

    Transition rows rather than open/closed intervals: there is no started/ended
    pair to keep consistent, no way to end up with two open rows for one screen,
    and no second write when a state ends. A state's duration is "until the next
    row, or now", and "offline since" is simply the current row's `at`.

    This is history, not state. Nothing reads it to answer "what is this screen
    doing now" -- that is always derived from last_seen and last_ping_ok via
    Screen.status_and_reason(). The recorded status can be up to one
    check_screens cycle behind reality, so the two are only ever compared, never
    substituted for one another.
    """

    screen = models.ForeignKey(
        Screen, on_delete=models.CASCADE, related_name="status_events")
    status = models.CharField(max_length=16, choices=ScreenStatus.choices)
    reason = models.CharField(max_length=16, choices=StatusReason.choices, blank=True)
    at = models.DateTimeField(db_index=True)

    class Meta:
        # Newest first: every reader of this table wants the latest transition,
        # and -pk breaks ties for rows written in the same cycle.
        ordering = ("-at", "-pk")
        verbose_name = "screen status change"
        verbose_name_plural = "screen status changes"

    def status_label(self):
        return ScreenStatus(self.status).label

    def reason_label(self):
        return StatusReason(self.reason).label if self.reason else ""

    def __str__(self):
        return f"{self.screen} → {self.status_label()} at {self.at:%Y-%m-%d %H:%M}"
