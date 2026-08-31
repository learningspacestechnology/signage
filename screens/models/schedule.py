from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from datetime import timedelta

from screens.models import Playlist


class Schedule(models.Model):
    name = models.TextField()
    description = models.TextField(blank=True)
    default_playlist = models.ForeignKey(Playlist, on_delete=models.PROTECT,
                                         help_text="Fallback playlist shown whenever no rule currently matches the date and time.")
    # Not exposed in the admin — see ScheduleDisplay. Still read by get_default().
    is_default = models.BooleanField(default=False,
                                     help_text="Marks the schedule used app-wide when a screen has none assigned. "
                                               "Only one schedule should be the default.")
    teams = models.ManyToManyField("screens.Team", related_name="schedules")

    def clean(self):
        super().clean()
        if self.pk and not self.teams.exists():
            raise ValidationError("Schedule must belong to at least one team.")

    def get_playlist(self):
        # Local (Europe/London) wall clock: `starts` is a DateField and
        # start_time/end_time are TimeFields keyed to civil time, and
        # django-recurrence works in naive datetime space -- so strip tz.
        # timezone.now() here would be aware UTC, so now.time() would be the UTC
        # wall clock and every rule would fire an hour late throughout BST.
        now = timezone.localtime().replace(tzinfo=None)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)
        playlist = self.default_playlist
        priority = 999999
        # Fetch rules that have already started; time-window filtering is done
        # in Python so that overnight rules (start_time > end_time) are handled
        # correctly -- the DB filter cannot express a window that wraps midnight.
        #
        # order_by is not cosmetic: ties on priority are resolved last-match-wins
        # below, and without an explicit ordering that depended on whatever row
        # order the backend happened to return.
        for rule in self.schedulerule_set.filter(starts__lte=now).order_by("priority", "pk"):
            if rule.priority > priority:
                continue
            # An all-day rule is stored as 00:00 -> 23:59:59.999999 by
            # ScheduleRule.before_save, so it does not read as a wrap here.
            overnight = rule.start_time > rule.end_time
            if overnight:
                in_window = now.time() >= rule.start_time or now.time() <= rule.end_time
            else:
                in_window = rule.start_time <= now.time() <= rule.end_time
            if not in_window:
                continue

            if overnight and now.time() <= rule.end_time:
                # Past midnight, so the occurrence that opened this window was
                # yesterday's.
                ref_start = yesterday_start
                ref_end = today_start
            else:
                ref_start = today_start
                ref_end = today_start + timedelta(days=1)

            # between() is exclusive at both ends, and a date-only DTSTART puts
            # its occurrences at midnight -- exactly on ref_start. Step back so
            # they are not dropped. ref_end is deliberately not extended, so
            # tomorrow's occurrence stays excluded.
            ref_start -= timedelta(seconds=1)

            # Normalise the stored dtstart to naive local civil time so that
            # dateutil generates naive occurrences comparable with ref_start /
            # ref_end. RecurrenceField serialises dtstart as UTC, so it comes
            # back aware and would raise on comparison.
            stored_dtstart = rule.occurrences.dtstart
            if stored_dtstart is not None and stored_dtstart.tzinfo is not None:
                normalized_dtstart = timezone.localtime(stored_dtstart).replace(tzinfo=None)
            else:
                # The admin's recurrence widget saves no DTSTART, so this is the
                # common path. Anchoring on "today" means a pattern with no day
                # selected (bare FREQ=WEEKLY) never fires -- see KNOWN_ISSUES.
                normalized_dtstart = stored_dtstart or ref_start
            if any(rule.occurrences.between(ref_start, ref_end, dtstart=normalized_dtstart)):
                playlist = rule.playlist
                priority = rule.priority

        return playlist

    @staticmethod
    def get_default():
        out = Schedule.objects.filter(is_default=True).first()
        if out:
            return out
        else:
            return None

    def __str__(self):
        return self.name
