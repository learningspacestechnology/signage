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
