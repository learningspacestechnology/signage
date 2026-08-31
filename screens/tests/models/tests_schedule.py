"""Schedule.get_playlist — which playlist is in force right now.

Rule times are LOCAL CIVIL time. `ScheduleRule.starts` is a DateField and
`start_time`/`end_time` are TimeFields holding what an operator typed off a wall
clock, and django-recurrence works in naive datetime space, so get_playlist
evaluates the whole thing in naive local time.

That is why these fixtures use `self._now()` rather than `timezone.now()`: under
USE_TZ=True the latter is aware UTC, so assigning it to a TimeField stores the
UTC wall clock. Fixtures built that way shared the very defect the code had
(KNOWN_ISSUES #9) and the suite could not fail while they did.

Every test pins the clock. Unpinned, these are seasonal — a BST bug is invisible
for five months of the year — and `test_get_expired_rule` is a genuine flake
between 00:00 and 00:01 local, where `start_time = now - 1m` wraps to the
previous day.
"""
from datetime import date, datetime, time, timedelta, timezone as dt_timezone

import recurrence
import time_machine
from django.test import TestCase
from django.utils import timezone

from screens.models import Playlist, Schedule

# time_machine reads a naive string as the local wall clock, and Django sets the
# process TZ from TIME_ZONE, so these are Europe/London civil times.
BST_NOON = "2024-06-15 12:00:00"   # 12:00 BST == 11:00Z
GMT_NOON = "2024-01-15 12:00:00"   # 12:00 GMT == 12:00Z


@time_machine.travel(BST_NOON, tick=False)
class ScheduleTests(TestCase):

    def setUp(self):
        self.default_list = Playlist.objects.create()
        self.schedule = Schedule.objects.create(default_playlist=self.default_list)
        self.list_a = Playlist.objects.create()
        self.list_b = Playlist.objects.create()
        self.list_c = Playlist.objects.create()

    def _now(self):
        """Naive local civil time — what the admin actually stores."""
        return timezone.localtime().replace(tzinfo=None)

    def make_current_daily_reccurence(self):
        rule = recurrence.Rule(recurrence.DAILY)
        return recurrence.Recurrence(
            dtstart=self._now() - timedelta(days=1),
            dtend=self._now() + timedelta(days=1),
            rrules=[rule]
        )

    def make_expired_daily_reccurence(self):
        rule = recurrence.Rule(recurrence.DAILY)
        return recurrence.Recurrence(
            dtstart=self._now() - timedelta(days=10),
            dtend=self._now() - timedelta(days=1),
            rrules=[rule]
        )

    def test_get_default_playlist(self):
        self.assertEqual(self.schedule.get_playlist(), self.default_list)

    def test_get_single_rule(self):
        self.schedule.schedulerule_set.create(
            playlist=self.list_a,
            priority=1,
            starts=self._now(),
            start_time=self._now() - timedelta(minutes=1),
            end_time=self._now() + timedelta(minutes=1),
            occurrences=self.make_current_daily_reccurence()
        )
        self.assertEqual(self.schedule.get_playlist(), self.list_a)

    def test_wrapping_window_excludes_its_own_hole(self):
        """start_time > end_time is a legitimate overnight window, not an error.

        Here the window is (now + 1m) -> (now - 1m): the whole day except a
        two-minute hole centred on now. The one instant it must NOT match is now.

        Before overnight support this passed vacuously, because a SQL BETWEEN
        can never satisfy start <= now <= end when start > end. It now passes
        because the wrap is evaluated properly and now falls in the hole.
        """
        self.schedule.schedulerule_set.create(
            playlist=self.list_a,
            priority=1,
            starts=self._now(),
            start_time=self._now() + timedelta(minutes=1),
            end_time=self._now() - timedelta(minutes=1),
            occurrences=self.make_current_daily_reccurence()
        )
        self.assertEqual(self.schedule.get_playlist(), self.default_list)

    def test_get_expired_rule(self):
        self.schedule.schedulerule_set.create(
            playlist=self.list_a,
            priority=1,
            starts=self._now() - timedelta(days=1),
            start_time=self._now() - timedelta(minutes=1),
            end_time=self._now() + timedelta(minutes=1),
            occurrences=self.make_expired_daily_reccurence()
        )
        self.assertEqual(self.schedule.get_playlist(), self.default_list)

    def test_get_future_rule(self):
        self.schedule.schedulerule_set.create(
            playlist=self.list_a,
            priority=1,
            starts=self._now() + timedelta(days=1),
            start_time=self._now() - timedelta(minutes=1),
            end_time=self._now() + timedelta(minutes=1),
            occurrences=self.make_current_daily_reccurence()
        )
        self.assertEqual(self.schedule.get_playlist(), self.default_list)

    def test_priorities(self):
        self.schedule.schedulerule_set.create(
            playlist=self.list_a,
            priority=10,
            starts=self._now() - timedelta(days=1),
            start_time=self._now() - timedelta(minutes=1),
            end_time=self._now() + timedelta(minutes=1),
            occurrences=self.make_current_daily_reccurence()
        )
        self.schedule.schedulerule_set.create(
            playlist=self.list_b,
            priority=1,
            starts=self._now() - timedelta(days=1),
            start_time=self._now() - timedelta(minutes=1),
            end_time=self._now() + timedelta(minutes=1),
            occurrences=self.make_current_daily_reccurence()
        )
        self.assertEqual(self.schedule.get_playlist(), self.list_b)

    # --- overnight / adjacent-day rules (ported from upstream 4d9c07d) -------

    def _make_daily_since(self, since: datetime):
        rule = recurrence.Rule(recurrence.DAILY)
        return recurrence.Recurrence(
            dtstart=since,
            rrules=[rule]
        )

    def _overnight_rule(self):
        """23:00 -> 01:00, i.e. a window that wraps midnight."""
        self.schedule.schedulerule_set.create(
            playlist=self.list_a,
            priority=1,
            starts=date(2024, 6, 1),
            start_time=time(23, 0),
            end_time=time(1, 0),
            occurrences=self._make_daily_since(datetime(2024, 6, 1)),
        )

    def _weekly_tuesday_rule(self, start_time, end_time):
        self.schedule.schedulerule_set.create(
            playlist=self.list_a,
            priority=1,
            starts=date(2024, 6, 1),
            start_time=start_time,
            end_time=end_time,
            occurrences=recurrence.Recurrence(
                dtstart=datetime(2024, 6, 4),  # Tuesday
                rrules=[recurrence.Rule(recurrence.WEEKLY)],
            ),
        )

    @time_machine.travel("2024-06-15 23:30:00", tick=False)
    def test_overnight_rule_active_before_midnight(self):
        """A window straddling midnight should match before midnight."""
        self._overnight_rule()
        self.assertEqual(self.schedule.get_playlist(), self.list_a)

    @time_machine.travel("2024-06-16 00:30:00", tick=False)
    def test_overnight_rule_active_after_midnight(self):
        """...and still match after it, against yesterday's occurrence."""
        self._overnight_rule()
        self.assertEqual(self.schedule.get_playlist(), self.list_a)

    @time_machine.travel("2024-06-15 12:00:00", tick=False)
    def test_overnight_rule_inactive_midday(self):
        self._overnight_rule()
        self.assertEqual(self.schedule.get_playlist(), self.default_list)

    @time_machine.travel("2024-06-15 01:30:00", tick=False)
    def test_overnight_rule_inactive_just_after_end(self):
        """A rule ending at 01:00 should not match at 01:30."""
        self._overnight_rule()
        self.assertEqual(self.schedule.get_playlist(), self.default_list)

    @time_machine.travel("2024-06-17 12:00:00", tick=False)  # Monday
    def test_weekly_rule_does_not_fire_the_day_before(self):
        """A weekly rule whose next occurrence is tomorrow must not fire today.

        The old code passed dtstart=yesterday to between(), re-anchoring the
        pattern on the wrong weekday.
        """
        self._weekly_tuesday_rule(time(11, 0), time(13, 0))
        self.assertEqual(self.schedule.get_playlist(), self.default_list)

    @time_machine.travel("2024-06-18 12:00:00", tick=False)  # Tuesday
    def test_weekly_rule_fires_on_correct_day(self):
        self._weekly_tuesday_rule(time(11, 0), time(13, 0))
        self.assertEqual(self.schedule.get_playlist(), self.list_a)

    @time_machine.travel("2024-06-19 00:30:00", tick=False)  # Wednesday 00:30
    def test_weekly_overnight_rule_active_after_midnight(self):
        """A weekly Tuesday 23:00-01:00 rule is still on at Wednesday 00:30."""
        self._weekly_tuesday_rule(time(23, 0), time(1, 0))
        self.assertEqual(self.schedule.get_playlist(), self.list_a)

    @time_machine.travel("2024-06-20 00:30:00", tick=False)  # Thursday 00:30
    def test_weekly_overnight_rule_inactive_wrong_day_after_midnight(self):
        self._weekly_tuesday_rule(time(23, 0), time(1, 0))
        self.assertEqual(self.schedule.get_playlist(), self.default_list)

    # BYDAY is how the admin widget actually stores "every Tuesday", so these
    # two are the sharpest tests here. Upstream wrote them but left them at
    # module level, where the loader never collected them, and double-wrapped
    # recurrence.TUESDAY (already a Weekday) so they errored once re-indented.

    def _byday_tuesday_rule(self):
        self.schedule.schedulerule_set.create(
            playlist=self.list_a,
            priority=1,
            starts=date(2024, 6, 1),
            start_time=time(11, 0),
            end_time=time(13, 0),
            occurrences=recurrence.Recurrence(
                dtstart=datetime(2024, 6, 1),
                rrules=[recurrence.Rule(
                    recurrence.WEEKLY,
                    byday=[recurrence.TUESDAY],
                )],
            ),
        )

    @time_machine.travel("2024-06-18 12:00:00", tick=False)  # Tuesday
    def test_byday_rule_fires_on_correct_day(self):
        self._byday_tuesday_rule()
        self.assertEqual(self.schedule.get_playlist(), self.list_a)

    @time_machine.travel("2024-06-17 12:00:00", tick=False)  # Monday
    def test_byday_rule_does_not_fire_on_wrong_day(self):
        self._byday_tuesday_rule()
        self.assertEqual(self.schedule.get_playlist(), self.default_list)

    @time_machine.travel("2024-06-17 12:00:00", tick=True)  # Monday, clock running
    def test_byday_rule_does_not_fire_the_day_before_on_a_running_clock(self):
        """tick=True on purpose -- this bug is invisible with a frozen clock.

        The old code asked `between(yesterday, tomorrow, dtstart=yesterday)`,
        re-anchoring each rule's pattern on yesterday and testing a 48-hour
        window. `yesterday` and `tomorrow` came from two separate
        timezone.now() calls, so in production that window was 48h + a few
        microseconds -- just wide enough to include tomorrow's occurrence.
        Measured against the real clock, a BYDAY=TU rule fired on Monday as
        well as Tuesday, and the admin's own BYDAY=MO,WE,FR shape fired six
        days a week.

        Frozen at tick=False the epsilon is exactly zero, the boundary lands on
        the excluded endpoint, and everything looks correct -- which is why
        neither repo's frozen tests ever caught it.
        """
        self._byday_tuesday_rule()
        self.assertEqual(self.schedule.get_playlist(), self.default_list)

    # --- rule times are LOCAL CIVIL time (KNOWN_ISSUES #9) -------------------
    #
    # get_playlist used to compare timezone.now().time() -- the UTC wall clock
    # -- against start_time/end_time, which operators enter as local civil time.
    # Under BST the two are an hour apart, so a 17:00-18:00 rule played
    # 18:00-19:00 and the default playlist covered the first hour. These are the
    # assertions that would have caught it; neither repo had them.

    def _evening_rule(self):
        """Daily 17:00-18:00, in the operator's own words."""
        self.schedule.schedulerule_set.create(
            playlist=self.list_a,
            priority=1,
            starts=date(2024, 1, 1),
            start_time=time(17, 0),
            end_time=time(18, 0),
            occurrences=recurrence.Recurrence(
                dtstart=datetime(2024, 1, 1),
                rrules=[recurrence.Rule(recurrence.DAILY)],
            ),
        )

    @time_machine.travel("2024-06-15 17:30:00", tick=False)  # 17:30 BST == 16:30Z
    def test_rule_is_active_at_its_local_start_during_bst(self):
        """The reported symptom: now.time() was 16:30Z, short of the window."""
        self._evening_rule()
        self.assertEqual(self.schedule.get_playlist(), self.list_a)

    @time_machine.travel("2024-06-15 18:30:00", tick=False)  # 18:30 BST == 17:30Z
    def test_rule_has_stopped_after_its_local_end_during_bst(self):
        """The other edge: the rule used to still be playing an hour late.

        Pinning both edges is what stops a sign flip in the conversion passing.
        """
        self._evening_rule()
        self.assertEqual(self.schedule.get_playlist(), self.default_list)

    @time_machine.travel("2024-01-15 17:30:00", tick=False)  # 17:30 GMT == 17:30Z
    def test_rule_is_active_at_its_local_start_during_gmt(self):
        """Winter control: local == UTC, so this passed before the fix too. It
        exists to prove the fix did not simply move the error into winter."""
        self._evening_rule()
        self.assertEqual(self.schedule.get_playlist(), self.list_a)

    @time_machine.travel("2024-01-15 18:30:00", tick=False)
    def test_rule_has_stopped_after_its_local_end_during_gmt(self):
        self._evening_rule()
        self.assertEqual(self.schedule.get_playlist(), self.default_list)

    # --- the two nights the clocks change ------------------------------------
    #
    # get_playlist works in naive local civil time, so on the autumn fall-back
    # day a window inside the repeated hour is active twice, and on the spring
    # forward day a window inside the skipped hour never happens at all. Both
    # are the honest reading of what "01:30" means on those nights; these pin
    # them so nobody "fixes" one into the other.
    #
    # Explicit UTC instants, not naive strings: time_machine silently resolves
    # "2024-03-31 01:30:00" to 02:30 (it does not exist) and picks the first
    # pass for "2024-10-27 01:30:00" (it happens twice).

    def _small_hours_rule(self, start, end):
        self.schedule.schedulerule_set.create(
            playlist=self.list_a, priority=1, starts=date(2024, 1, 1),
            start_time=start, end_time=end,
            occurrences=recurrence.Recurrence(
                dtstart=datetime(2024, 1, 1),
                rrules=[recurrence.Rule(recurrence.DAILY)],
            ),
        )

    @time_machine.travel(datetime(2024, 10, 27, 0, 30, tzinfo=dt_timezone.utc), tick=False)
    def test_rule_active_in_first_pass_of_repeated_hour(self):
        """00:30Z is 01:30 BST -- the first pass of 2024-10-27 01:30."""
        self._small_hours_rule(time(1, 0), time(2, 0))
        self.assertEqual(self.schedule.get_playlist(), self.list_a)

    @time_machine.travel(datetime(2024, 10, 27, 1, 30, tzinfo=dt_timezone.utc), tick=False)
    def test_rule_active_in_second_pass_of_repeated_hour(self):
        """01:30Z is 01:30 GMT -- the same wall clock, an hour later. The rule
        is genuinely on air for two hours that night."""
        self._small_hours_rule(time(1, 0), time(2, 0))
        self.assertEqual(self.schedule.get_playlist(), self.list_a)

    @time_machine.travel(datetime(2024, 3, 31, 1, 30, tzinfo=dt_timezone.utc), tick=False)
    def test_rule_inside_skipped_hour_never_fires(self):
        """01:30Z is 02:30 BST: local 01:00-01:59 does not exist on 2024-03-31,
        so a rule confined to it simply does not run that night."""
        self._small_hours_rule(time(1, 0), time(1, 59))
        self.assertEqual(self.schedule.get_playlist(), self.default_list)

    # --- documented trap, not a regression -----------------------------------

    def test_a_rule_with_no_day_selected_never_fires(self):
        """A bare FREQ=WEEKLY never fires: no DTSTART means the anchor falls back
        to "today", so the next occurrence is always a week away.

        ScheduleRule.clean() now refuses to save such a rule, so this should be
        unreachable through the admin. It is pinned here anyway, created through
        the ORM to bypass validation, because it documents *why* the validation
        exists -- and because anything already in the database from before it
        still behaves this way.
        """
        self.schedule.schedulerule_set.create(
            playlist=self.list_a,
            priority=1,
            starts=date(2024, 6, 1),
            start_time=time(11, 0),
            end_time=time(13, 0),
            occurrences=recurrence.deserialize('RRULE:FREQ=WEEKLY'),
        )
        self.assertEqual(self.schedule.get_playlist(), self.default_list)
