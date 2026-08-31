"""Three-state screen status: the tiers, the probe, and the history it records.

Status answers two different questions from two independent signals. `last_seen`
says "the player is polling"; `last_ping_ok` says "the box is on the network".
The amber state is the gap between them, and it is the one worth getting right:
it is the difference between sending someone to restart a browser and sending
them to check a power cable.
"""
import datetime
from unittest import mock

import time_machine
from django.test import TestCase, override_settings
from django.utils import timezone

from screens.models import (
    Playlist, Schedule, Screen, ScreenStatus, ScreenStatusEvent, StatusReason)
from screens.models.screen import ATTENTION_WINDOW, ONLINE_WINDOW, PING_WINDOW
from screens.tasks import (
    _probe_screens, _record_status_transitions, check_screens,
    cleanup_status_events)

NOW = datetime.datetime.fromisoformat("2030-06-01T12:00:00+00:00")


class ScreenStatusTestCase(TestCase):
    def setUp(self):
        playlist = Playlist.objects.create(name="base")
        self.schedule = Schedule.objects.create(name="s", default_playlist=playlist)

    def make_screen(self, name="scr", ip="10.0.0.9", **state):
        """A screen with its timestamps written past the auto_now_add value."""
        screen = Screen.objects.create(name=name, ip=ip, schedule=self.schedule)
        if state:
            Screen.objects.filter(pk=screen.pk).update(**state)
        screen.refresh_from_db()
        return screen


class StatusTierTests(ScreenStatusTestCase):
    def test_a_recent_heartbeat_is_online(self):
        screen = self.make_screen(last_seen=timezone.now())
        self.assertEqual(screen.status_and_reason(), (ScreenStatus.ONLINE, ""))
        self.assertTrue(screen.online())

    def test_a_reachable_screen_that_stopped_reporting_is_amber(self):
        """The state the whole feature exists for: alive, but not doing its job."""
        screen = self.make_screen(
            last_seen=timezone.now() - datetime.timedelta(days=2),
            last_ping_ok=timezone.now(),
            last_ping_attempt=timezone.now(),
        )
        self.assertEqual(
            screen.status_and_reason(),
            (ScreenStatus.ATTENTION, StatusReason.PING_ONLY))
        self.assertFalse(screen.online())

    def test_a_screen_that_only_just_stopped_reporting_is_amber(self):
        """The grace tier, which needs no probe at all: one missed poll is not
        death, so amber still means something with probing turned off."""
        screen = self.make_screen(
            last_seen=timezone.now() - ONLINE_WINDOW - datetime.timedelta(seconds=30))
        self.assertEqual(
            screen.status_and_reason(),
            (ScreenStatus.ATTENTION, StatusReason.RECENTLY_LOST))

    def test_ping_beats_grace(self):
        """Both tiers match; the more informative reason has to win, or a
        reachable screen would be reported as merely 'recently lost'."""
        screen = self.make_screen(
            last_seen=timezone.now() - ONLINE_WINDOW - datetime.timedelta(seconds=30),
            last_ping_ok=timezone.now(),
        )
        self.assertEqual(
            screen.status_and_reason(),
            (ScreenStatus.ATTENTION, StatusReason.PING_ONLY))

    def test_probed_and_silent_is_offline_with_no_response(self):
        screen = self.make_screen(
            last_seen=timezone.now() - datetime.timedelta(days=2),
            last_ping_attempt=timezone.now(),
        )
        self.assertEqual(
            screen.status_and_reason(),
            (ScreenStatus.OFFLINE, StatusReason.NO_RESPONSE))

    def test_never_probed_and_silent_is_offline_with_no_contact(self):
        """Distinct from the above on purpose. 'We asked and got nothing' and
        'we never asked' are different claims, and probing is off by default."""
        screen = self.make_screen(
            last_seen=timezone.now() - datetime.timedelta(days=2))
        self.assertEqual(
            screen.status_and_reason(),
            (ScreenStatus.OFFLINE, StatusReason.NO_CONTACT))

    def test_a_stale_ping_stops_holding_a_screen_amber(self):
        screen = self.make_screen(
            last_seen=timezone.now() - datetime.timedelta(days=2),
            last_ping_ok=timezone.now() - PING_WINDOW - datetime.timedelta(minutes=1),
            last_ping_attempt=timezone.now(),
        )
        self.assertEqual(screen.status(), ScreenStatus.OFFLINE)

    def test_ping_window_outlasts_the_probe_cadence(self):
        """A single missed probe must not flip a reachable screen to red, so the
        window has to be longer than the interval check_screens runs at."""
        from django.conf import settings
        entry = settings.CELERY_BEAT_SCHEDULE['check-screens-every-5-minutes']
        self.assertGreater(PING_WINDOW.total_seconds(), entry['schedule'])


class StatusAnnotationAgreementTests(ScreenStatusTestCase):
    """The SQL and Python halves of the tiers must never disagree.

    They are built from one definition in Screen._status_tiers(), so this is
    the test that fails if someone edits one branch and not the other -- the
    same guarantee the changelist filter has had since online_cutoff() was
    shared with it.
    """

    def test_every_combination_agrees(self):
        offsets = (
            None,
            datetime.timedelta(0),
            ONLINE_WINDOW,
            ONLINE_WINDOW + datetime.timedelta(seconds=1),
            ATTENTION_WINDOW,
            ATTENTION_WINDOW + datetime.timedelta(seconds=1),
            PING_WINDOW,
            PING_WINDOW + datetime.timedelta(seconds=1),
            datetime.timedelta(days=30),
        )
        # Frozen so the Python predicates and the Q objects are built from the
        # same instant; a real clock would let them straddle a boundary.
        with time_machine.travel(NOW, tick=False):
            now = timezone.now()
            expected = {}
            for i, seen in enumerate(o for o in offsets if o is not None):
                for j, ping in enumerate(offsets):
                    screen = self.make_screen(
                        name=f"s{i}-{j}", ip=f"10.1.{i}.{j}",
                        last_seen=now - seen,
                        last_ping_ok=None if ping is None else now - ping,
                        last_ping_attempt=None if ping is None else now - ping,
                    )
                    expected[screen.pk] = screen.status_and_reason()

            for row in Screen.objects.with_status():
                self.assertEqual(
                    (row.derived_status, row.derived_reason),
                    expected[row.pk],
                    f"annotation and status_and_reason() disagree for {row.name}",
                )

    def test_the_rank_orders_by_severity_not_alphabetically(self):
        with time_machine.travel(NOW, tick=False):
            now = timezone.now()
            self.make_screen(name="green", ip="10.2.0.1", last_seen=now)
            self.make_screen(name="amber", ip="10.2.0.2",
                             last_seen=now - datetime.timedelta(days=1),
                             last_ping_ok=now)
            self.make_screen(name="red", ip="10.2.0.3",
                             last_seen=now - datetime.timedelta(days=1))
            ranked = list(
                Screen.objects.with_status().order_by("status_rank")
                .values_list("name", flat=True))
        self.assertEqual(ranked, ["green", "amber", "red"])

    def test_needing_attention_puts_amber_before_red(self):
        with time_machine.travel(NOW, tick=False):
            now = timezone.now()
            self.make_screen(name="green", ip="10.3.0.1", last_seen=now)
            self.make_screen(name="red", ip="10.3.0.2",
                             last_seen=now - datetime.timedelta(days=9))
            self.make_screen(name="amber", ip="10.3.0.3",
                             last_seen=now - datetime.timedelta(days=1),
                             last_ping_ok=now)
            names = list(
                Screen.objects.needing_attention().values_list("name", flat=True))
        self.assertEqual(names, ["amber", "red"])


@override_settings(SCREEN_PROBE_ENABLED=True, SCREEN_PROBE_TIMEOUT=1,
                   SCREEN_PROBE_CONCURRENCY=4)
class ProbeTaskTests(ScreenStatusTestCase):
    def setUp(self):
        super().setUp()
        self.dark = self.make_screen(
            name="dark", ip="10.4.0.1",
            last_seen=timezone.now() - datetime.timedelta(days=1))
        self.live = self.make_screen(
            name="live", ip="10.4.0.2", last_seen=timezone.now())

    @staticmethod
    def _run(returncode=0):
        return mock.patch("screens.tasks.subprocess.run",
                          return_value=mock.Mock(returncode=returncode))

    def test_a_reachable_screen_is_recorded_and_turns_amber(self):
        with mock.patch("screens.tasks.shutil.which", return_value="/bin/ping"), \
                self._run(returncode=0):
            self.assertEqual(_probe_screens(), 1)
        self.dark.refresh_from_db()
        self.assertIsNotNone(self.dark.last_ping_ok)
        self.assertIsNotNone(self.dark.last_ping_attempt)
        self.assertEqual(self.dark.status(), ScreenStatus.ATTENTION)

    def test_an_unreachable_screen_records_the_attempt_only(self):
        with mock.patch("screens.tasks.shutil.which", return_value="/bin/ping"), \
                self._run(returncode=1):
            _probe_screens()
        self.dark.refresh_from_db()
        self.assertIsNone(self.dark.last_ping_ok)
        self.assertIsNotNone(self.dark.last_ping_attempt)
        self.assertEqual(
            self.dark.status_and_reason(),
            (ScreenStatus.OFFLINE, StatusReason.NO_RESPONSE))

    def test_a_reporting_screen_is_not_probed(self):
        """Probing a screen that is already polling adds network traffic and
        answers a question we have a better answer to."""
        with mock.patch("screens.tasks.shutil.which", return_value="/bin/ping"), \
                self._run(returncode=0) as run:
            _probe_screens()
        probed = {call.args[0][-1] for call in run.call_args_list}
        self.assertEqual(probed, {"10.4.0.1"})
        self.live.refresh_from_db()
        self.assertIsNone(self.live.last_ping_attempt)

    def test_a_timeout_counts_as_unreachable(self):
        import subprocess
        with mock.patch("screens.tasks.shutil.which", return_value="/bin/ping"), \
                mock.patch("screens.tasks.subprocess.run",
                           side_effect=subprocess.TimeoutExpired("ping", 3)):
            _probe_screens()
        self.dark.refresh_from_db()
        self.assertIsNone(self.dark.last_ping_ok)
        self.assertIsNotNone(self.dark.last_ping_attempt)

    def test_a_missing_ping_binary_writes_nothing(self):
        """"We cannot probe" must not be recorded as "the screen did not
        answer" -- that would turn a deployment gap into a fault report."""
        with mock.patch("screens.tasks.shutil.which", return_value=None):
            with self.assertLogs("screens.tasks", level="WARNING") as logs:
                self.assertEqual(_probe_screens(), 0)
        self.assertIn("iputils-ping", logs.output[0])
        self.dark.refresh_from_db()
        self.assertIsNone(self.dark.last_ping_attempt)

    @override_settings(SCREEN_PROBE_ENABLED=False)
    def test_disabled_probing_writes_nothing_and_leaves_status_binary(self):
        with mock.patch("screens.tasks.subprocess.run") as run:
            self.assertEqual(_probe_screens(), 0)
        run.assert_not_called()
        self.dark.refresh_from_db()
        self.assertIsNone(self.dark.last_ping_ok)
        self.assertEqual(
            self.dark.status_and_reason(),
            (ScreenStatus.OFFLINE, StatusReason.NO_CONTACT))

    def test_a_probe_cycle_does_not_move_the_publish_timestamp(self):
        """The regression that would restart every device's rotation once per
        cycle. Screen.last_updated is auto_now and is the publish signal, which
        is why the probe writes through a queryset .update().
        """
        before = dict(Screen.objects.values_list("pk", "last_updated"))
        with time_machine.travel(NOW, tick=False):
            with mock.patch("screens.tasks.shutil.which", return_value="/bin/ping"), \
                    self._run(returncode=0):
                check_screens()
        self.assertEqual(dict(Screen.objects.values_list("pk", "last_updated")), before)
        # ...and the cycle really did write, so the assertion above has teeth.
        self.assertIsNotNone(Screen.objects.get(pk=self.dark.pk).last_ping_ok)

    def test_an_ipv6_screen_is_probed_over_ipv6(self):
        self.make_screen(name="v6", ip="2001:db8::1",
                         last_seen=timezone.now() - datetime.timedelta(days=1))
        with mock.patch("screens.tasks.shutil.which", return_value="/bin/ping"), \
                self._run(returncode=0) as run:
            _probe_screens()
        families = {call.args[0][1] for call in run.call_args_list}
        self.assertEqual(families, {"-4", "-6"})


class StatusHistoryTests(ScreenStatusTestCase):
    def test_a_transition_is_recorded_once(self):
        screen = self.make_screen(last_seen=timezone.now())
        self.assertEqual(_record_status_transitions(), 1)
        self.assertEqual(_record_status_transitions(), 0)
        event = screen.status_events.get()
        self.assertEqual(event.status, ScreenStatus.ONLINE)
        self.assertEqual(event.reason, "")

    def test_going_dark_appends_a_second_row(self):
        screen = self.make_screen(last_seen=timezone.now())
        _record_status_transitions()
        Screen.objects.filter(pk=screen.pk).update(
            last_seen=timezone.now() - datetime.timedelta(days=1))
        self.assertEqual(_record_status_transitions(), 1)
        self.assertEqual(
            list(screen.status_events.values_list("status", flat=True)),
            [ScreenStatus.OFFLINE, ScreenStatus.ONLINE],  # Meta.ordering: newest first
        )

    def test_a_change_of_reason_alone_is_a_transition(self):
        """Amber for two different reasons is two different situations, and the
        history would be misleading if only the status were compared."""
        screen = self.make_screen(
            last_seen=timezone.now() - ONLINE_WINDOW - datetime.timedelta(seconds=30))
        _record_status_transitions()
        Screen.objects.filter(pk=screen.pk).update(last_ping_ok=timezone.now())
        self.assertEqual(_record_status_transitions(), 1)
        self.assertEqual(
            list(screen.status_events.values_list("reason", flat=True)),
            [StatusReason.PING_ONLY, StatusReason.RECENTLY_LOST],
        )

    def test_status_since_reads_off_the_latest_event(self):
        screen = self.make_screen()
        with time_machine.travel(NOW, tick=False):
            Screen.objects.filter(pk=screen.pk).update(last_seen=timezone.now())
            _record_status_transitions()
            row = Screen.objects.with_status().get(pk=screen.pk)
            self.assertEqual(row.status_since, NOW)
            self.assertEqual(row.recorded_status, ScreenStatus.ONLINE)
            self.assertEqual(row.recorded_status, row.derived_status)

    def test_recorded_status_lags_the_derived_one_between_cycles(self):
        """The reason the admin only shows a "since" while the two agree: the
        recorded value is as old as the last check_screens run, and a screen
        can go dark in between."""
        screen = self.make_screen(last_seen=timezone.now())
        _record_status_transitions()
        Screen.objects.filter(pk=screen.pk).update(
            last_seen=timezone.now() - datetime.timedelta(days=1))
        row = Screen.objects.with_status().get(pk=screen.pk)
        self.assertEqual(row.recorded_status, ScreenStatus.ONLINE)
        self.assertEqual(row.derived_status, ScreenStatus.OFFLINE)


class StatusHistoryRetentionTests(ScreenStatusTestCase):
    @override_settings(SCREEN_STATUS_HISTORY_DAYS=30)
    def test_old_rows_go_but_the_latest_one_stays(self):
        """A screen dark for six months must not lose the row that says when it
        went dark -- that row is the entire answer to 'since when'."""
        screen = self.make_screen()
        now = timezone.now()
        old = ScreenStatusEvent.objects.create(
            screen=screen, status=ScreenStatus.ONLINE, reason="",
            at=now - datetime.timedelta(days=200))
        latest = ScreenStatusEvent.objects.create(
            screen=screen, status=ScreenStatus.OFFLINE,
            reason=StatusReason.NO_CONTACT,
            at=now - datetime.timedelta(days=190))
        recent = ScreenStatusEvent.objects.create(
            screen=screen, status=ScreenStatus.ONLINE, reason="",
            at=now)
        # `recent` is newest, so `latest` is prunable by age -- only `old` and
        # `latest` should go.
        cleanup_status_events()
        surviving = set(ScreenStatusEvent.objects.values_list("pk", flat=True))
        self.assertEqual(surviving, {recent.pk})
        self.assertFalse(ScreenStatusEvent.objects.filter(pk__in=[old.pk, latest.pk]))

    @override_settings(SCREEN_STATUS_HISTORY_DAYS=30)
    def test_a_screens_only_row_survives_any_age(self):
        screen = self.make_screen()
        event = ScreenStatusEvent.objects.create(
            screen=screen, status=ScreenStatus.OFFLINE,
            reason=StatusReason.NO_CONTACT,
            at=timezone.now() - datetime.timedelta(days=400))
        cleanup_status_events()
        self.assertTrue(ScreenStatusEvent.objects.filter(pk=event.pk).exists())
