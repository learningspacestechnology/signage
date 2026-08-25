"""ScheduleRule.is_expired, and the Celery task that deletes what it flags.

cleanup_schedule removes rows irreversibly and had no coverage at all. The
awkward part is that django-recurrence generates occurrences in whatever
awareness the stored dtstart carries: RecurrenceField serialises dtstart as UTC,
so a rule saved with one comes back aware, while a rule saved without one --
which is everything the admin's recurrence widget produces -- generates naive.

Mixing the two raises, and because cleanup_schedule filters with a lambda over
every rule, a single aware row used to abort the entire task. That is what
test_is_expired_handles_a_stored_dtstart and
test_cleanup_survives_a_rule_with_a_stored_dtstart exist to stop.
"""
from datetime import date, datetime, time, timedelta

import recurrence
import time_machine
from django.core.exceptions import ValidationError
from django.test import TestCase

from screens.models import Playlist, Schedule, ScheduleRule
from screens.tasks import cleanup_schedule

# Fixed so "two days ago" is never ambiguous and the suite does not drift.
NOW = "2026-06-15 12:00:00"


@time_machine.travel(NOW, tick=False)
class IsExpiredTests(TestCase):

    def setUp(self):
        self.playlist = Playlist.objects.create(name="p")
        self.schedule = Schedule.objects.create(
            name="s", default_playlist=Playlist.objects.create(name="d"))

    def make_rule(self, occurrences):
        # Deliberately not end_time=time(0, 0): before_save would rewrite it.
        return self.schedule.schedulerule_set.create(
            playlist=self.playlist,
            priority=1,
            starts=date(2024, 1, 1),
            start_time=time(9, 0),
            end_time=time(17, 0),
            occurrences=occurrences,
        )

    def test_is_expired_false_for_an_open_ended_rule(self):
        """No DTSTART and no end -- the shape the admin widget saves."""
        rule = self.make_rule(recurrence.deserialize('RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR'))
        rule.refresh_from_db()
        self.assertFalse(rule.is_expired())

    def test_is_expired_true_for_a_finished_rule(self):
        rule = self.make_rule(recurrence.Recurrence(
            dtstart=datetime(2024, 1, 1),
            dtend=datetime(2024, 3, 1),
            rrules=[recurrence.Rule(recurrence.DAILY)],
        ))
        rule.refresh_from_db()
        self.assertTrue(rule.is_expired())

    def test_is_expired_handles_a_stored_dtstart(self):
        """The regression test. A recurrence saved WITH a dtstart round-trips
        aware through RecurrenceField, and comparing it against a naive cutoff
        raises TypeError -- on the old line and on upstream's replacement
        alike. This must return a bool, not blow up."""
        rule = self.make_rule(recurrence.Recurrence(
            dtstart=datetime(2024, 1, 1),
            rrules=[recurrence.Rule(recurrence.DAILY)],
        ))
        rule.refresh_from_db()
        self.assertIs(rule.is_expired(), False)

    def test_is_expired_false_inside_the_two_day_grace(self):
        """A rule that ended yesterday is still within the grace window, so it
        survives one more cleanup pass."""
        rule = self.make_rule(recurrence.Recurrence(
            dtstart=datetime(2026, 6, 1),
            dtend=datetime(2026, 6, 14),
            rrules=[recurrence.Rule(recurrence.DAILY)],
        ))
        rule.refresh_from_db()
        self.assertFalse(rule.is_expired())


@time_machine.travel(NOW, tick=False)
class CleanupScheduleTaskTests(TestCase):

    def setUp(self):
        self.playlist = Playlist.objects.create(name="p")
        self.schedule = Schedule.objects.create(
            name="s", default_playlist=Playlist.objects.create(name="d"))

    def make_rule(self, occurrences):
        return self.schedule.schedulerule_set.create(
            playlist=self.playlist, priority=1, starts=date(2024, 1, 1),
            start_time=time(9, 0), end_time=time(17, 0), occurrences=occurrences)

    def test_cleanup_deletes_only_finished_rules(self):
        live = self.make_rule(recurrence.deserialize('RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR'))
        finished = self.make_rule(recurrence.Recurrence(
            dtstart=datetime(2024, 1, 1),
            dtend=datetime(2024, 3, 1),
            rrules=[recurrence.Rule(recurrence.DAILY)],
        ))

        cleanup_schedule()

        surviving = set(ScheduleRule.objects.values_list("pk", flat=True))
        self.assertIn(live.pk, surviving)
        self.assertNotIn(finished.pk, surviving)

    def test_cleanup_survives_a_rule_with_a_stored_dtstart(self):
        """One aware row used to raise TypeError out of the filter() lambda and
        abort the task, so nothing at all got cleaned up."""
        awkward = self.make_rule(recurrence.Recurrence(
            dtstart=datetime(2024, 1, 1),
            rrules=[recurrence.Rule(recurrence.DAILY)],
        ))
        finished = self.make_rule(recurrence.Recurrence(
            dtstart=datetime(2024, 1, 1),
            dtend=datetime(2024, 3, 1),
            rrules=[recurrence.Rule(recurrence.DAILY)],
        ))

        cleanup_schedule()

        surviving = set(ScheduleRule.objects.values_list("pk", flat=True))
        self.assertIn(awkward.pk, surviving)
        self.assertNotIn(finished.pk, surviving)


class IncompletePatternValidationTests(TestCase):
    """A pattern that never names a day is missing data, not a valid rule.

    Tick "Weekly", select no day, and django-recurrence stores a bare
    RRULE:FREQ=WEEKLY. dateutil silently substitutes the weekday of DTSTART --
    and the admin widget writes no DTSTART, so there is nothing stable to
    substitute. The rule saves cleanly and then never plays, with nothing
    anywhere to say why. ScheduleRule.clean refuses it instead.

    These go through full_clean() rather than the ORM on purpose: that is the
    path the admin inline takes, and it is the only path clean() runs on.
    """

    def setUp(self):
        self.playlist = Playlist.objects.create(name="p")
        self.schedule = Schedule.objects.create(
            name="s", default_playlist=Playlist.objects.create(name="d"))

    def rule(self, occurrences):
        return ScheduleRule(
            schedule=self.schedule, playlist=self.playlist, priority=1,
            starts=date(2024, 1, 1), start_time=time(9, 0), end_time=time(17, 0),
            occurrences=occurrences)

    def assertRejected(self, serialized, expected_fragment):
        rule = self.rule(recurrence.deserialize(serialized))
        with self.assertRaises(ValidationError) as caught:
            rule.full_clean()
        self.assertIn("occurrences", caught.exception.error_dict)
        self.assertIn(expected_fragment,
                      " ".join(caught.exception.messages))

    def assertAccepted(self, serialized):
        self.rule(recurrence.deserialize(serialized)).full_clean()

    def test_weekly_with_no_day_is_rejected(self):
        self.assertRejected('RRULE:FREQ=WEEKLY', "day of the week")

    def test_monthly_with_no_date_is_rejected(self):
        self.assertRejected('RRULE:FREQ=MONTHLY', "date of the month")

    def test_yearly_with_no_month_is_rejected(self):
        self.assertRejected('RRULE:FREQ=YEARLY', "at least one month")

    def test_yearly_with_a_month_but_no_day_is_rejected(self):
        """BYMONTH alone still leaves the day-of-month defaulting to today, so
        "every March" is as under-specified as "every year"."""
        self.assertRejected('RRULE:FREQ=YEARLY;BYMONTH=3', "at least one month")

    def test_a_second_incomplete_rule_is_still_caught(self):
        """Rules are validated individually; a good one does not excuse a bad one."""
        self.assertRejected(
            'RRULE:FREQ=WEEKLY;BYDAY=MO\nRRULE:FREQ=MONTHLY', "date of the month")

    # --- shapes that must keep working ---

    def test_daily_needs_nothing(self):
        """"Every day" is already complete -- there is no day left to choose."""
        self.assertAccepted('RRULE:FREQ=DAILY')

    def test_weekly_with_days_is_accepted(self):
        self.assertAccepted('RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR')

    def test_monthly_by_date_is_accepted(self):
        self.assertAccepted('RRULE:FREQ=MONTHLY;BYMONTHDAY=15')

    def test_monthly_by_last_day_of_month_is_accepted(self):
        """A negative BYMONTHDAY is a real date, not a malformed one: -1 is the
        last day of the month and tracks month length (30 June, 29 Feb)."""
        self.assertAccepted('RRULE:FREQ=MONTHLY;BYMONTHDAY=-1')

    def test_monthly_by_weekday_position_is_accepted(self):
        """"First Monday of the month" names a day without naming a date."""
        self.assertAccepted('RRULE:FREQ=MONTHLY;BYDAY=MO;BYSETPOS=1')

    def test_yearly_fully_specified_is_accepted(self):
        self.assertAccepted('RRULE:FREQ=YEARLY;BYMONTH=3;BYMONTHDAY=1')

    def test_explicit_dates_with_no_rule_are_accepted(self):
        """A recurrence can be nothing but RDATEs, which name their days exactly."""
        self.assertAccepted('RDATE:20240617T000000Z')

    def test_a_bare_weekly_with_its_own_dtstart_is_accepted(self):
        """With a stored DTSTART the fallback anchors to a real date rather than
        a moving one, so "every week from this date" is well defined. This is the
        shape our own ported upstream tests use."""
        self.rule(recurrence.Recurrence(
            dtstart=datetime(2024, 6, 4),
            rrules=[recurrence.Rule(recurrence.WEEKLY)],
        )).full_clean()
