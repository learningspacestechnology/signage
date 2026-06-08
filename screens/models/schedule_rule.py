from datetime import datetime

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
        return not bool(self.occurrences.after(timezone.datetime.today() - timezone.timedelta(days=2), inc=True))


@receiver(pre_save, sender=ScheduleRule)
def before_save(sender, **kwargs):
    if kwargs['instance'].end_time == datetime.min.time():
        kwargs['instance'].end_time = datetime.max.time()
