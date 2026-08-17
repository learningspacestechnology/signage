from datetime import datetime, timedelta

from django.db.models.signals import post_save, pre_save
from django.dispatch import Signal, receiver
from django.utils import timezone

from django.db import models
from recurrence.fields import RecurrenceField

from screens.models.playlist import Playlist
from screens.models.schedule import Schedule


class ScheduleRule(models.Model):
    playlist = models.ForeignKey(to=Playlist, on_delete=models.CASCADE,
                                 help_text="The playlist shown while this rule is active.")
    schedule = models.ForeignKey(to=Schedule, on_delete=models.CASCADE)
    starts = models.DateField(
        help_text="The rule is inactive until this date. Use it to schedule a rule to begin in the future.")
    occurrences = RecurrenceField(
        help_text="Which days the rule fires, as a repeating pattern (e.g. every Monday and Wednesday). "
                  "The rule only applies on matching days.")
    start_time = models.TimeField(
        help_text="Time of day the rule's playlist becomes active (on matching days).")
    end_time = models.TimeField(
        help_text="Time of day the rule's playlist stops being active. Set to 00:00 (midnight) to mean end of day.")
    priority = models.IntegerField(
        help_text="When several rules match the same moment, the one with the LOWEST priority number wins "
                  "(lower number = higher precedence). If none match, the schedule's default playlist is shown.")

    def is_expired(self):
        """Has this rule's pattern finished for good?

        Read by the cleanup_schedule Celery task, which DELETES whatever this
        returns True for -- so a raise here is worse than a wrong answer.

        django-recurrence generates occurrences in whatever awareness its
        dtstart carries. RecurrenceField serialises dtstart as UTC, so a rule
        saved with one deserialises aware, while a rule saved without one (what
        the admin widget produces) generates naive. Comparing the two raises
        "can't compare offset-naive and offset-aware datetimes", and because
        cleanup_schedule filters with a lambda over every rule, one such row
        aborts the whole task and nothing gets cleaned up.

        So normalise both sides to naive local civil time, consistently with
        Schedule.get_playlist. Note upstream's c80aa01 fixes only the cutoff and
        still raises on the dtstart; this deliberately goes further.
        """
        cutoff = timezone.localtime().replace(tzinfo=None) - timedelta(days=2)
        dtstart = self.occurrences.dtstart
        if dtstart is not None and timezone.is_aware(dtstart):
            dtstart = timezone.localtime(dtstart).replace(tzinfo=None)
        return not bool(self.occurrences.after(cutoff, inc=True, dtstart=dtstart))


@receiver(pre_save, sender=ScheduleRule)
def before_save(sender, **kwargs):
    """Store "end of day" as 23:59:59.999999 rather than 00:00.

    Load-bearing for Schedule.get_playlist, which reads start_time > end_time as
    a window that wraps midnight: without this rewrite an all-day 00:00-00:00
    rule would look like a wrap, and a 09:00-00:00 rule would run all night.
    """
    if kwargs['instance'].end_time == datetime.min.time():
        kwargs['instance'].end_time = datetime.max.time()
