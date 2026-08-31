from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.db.models.signals import post_save, pre_save
from django.dispatch import Signal, receiver
from django.utils import timezone

import recurrence
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
                  "The rule only applies on matching days. Pick a frequency and then the days it "
                  "applies to — a pattern with nothing chosen doesn't say when to run and won't save. "
                  "In the monthly grid, the four cells after 31 are counted back from the end of the "
                  "month, so −1 is the last day whether that's the 28th, 29th, 30th or 31st.")
    start_time = models.TimeField(
        help_text="Time of day the rule's playlist becomes active (on matching days).")
    end_time = models.TimeField(
        help_text="Time of day the rule's playlist stops being active. Set to 00:00 (midnight) to mean end of day.")
    priority = models.IntegerField(
        help_text="When several rules match the same moment, the one with the LOWEST priority number wins "
                  "(lower number = higher precedence). If none match, the schedule's default playlist is shown.")

    # What each frequency needs before it names an actual day, as
    # (test, message). DAILY is absent because "every day" is already complete.
    _INCOMPLETE_PATTERN = {
        recurrence.WEEKLY: (
            lambda r: not r.byday,
            "Choose at least one day of the week. A weekly pattern with no day "
            "selected doesn't say when to run.",
        ),
        recurrence.MONTHLY: (
            lambda r: not (r.bymonthday or r.byday),
            "Choose at least one date of the month, or a weekday position such "
            "as 'first Monday'. A monthly pattern with neither doesn't say when "
            "to run.",
        ),
        recurrence.YEARLY: (
            lambda r: not (r.bymonth and (r.bymonthday or r.byday)),
            "Choose at least one month, and a date or weekday position within "
            "it. A yearly pattern needs both to say when to run.",
        ),
    }

    def clean(self):
        """Refuse a pattern that never names a day.

        Tick "Weekly" and select no day, and django-recurrence saves a bare
        RRULE:FREQ=WEEKLY. dateutil does not treat that as an error -- it falls
        back to the weekday of DTSTART, and the admin's widget writes no DTSTART,
        so the anchor becomes whenever the rule happens to be evaluated. Under
        get_playlist's one-day window that resolves to nothing and the rule
        silently never fires. Same for MONTHLY with no date, and for YEARLY,
        which needs a month *and* a day within it -- BYMONTH alone still leaves
        the day-of-month defaulting to "today".

        Every one of these means the operator started choosing a pattern and did
        not finish. Saying so here is far better than saving something that looks
        configured, shows no error, and simply never plays.

        Skipped when the recurrence carries its own DTSTART: the fallback is then
        anchored to a real stored date rather than a moving one, so "every week
        from this date" is a well-defined thing to have meant.
        """
        super().clean()
        if not self.occurrences:
            return
        if self.occurrences.dtstart is not None:
            return
        for rule in self.occurrences.rrules:
            incomplete = self._INCOMPLETE_PATTERN.get(rule.freq)
            if incomplete and incomplete[0](rule):
                raise ValidationError({"occurrences": incomplete[1]})

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
