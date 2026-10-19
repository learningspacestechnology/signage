import datetime
import logging
from io import StringIO

from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import Group, User
from django.contrib.sessions.backends.db import SessionStore
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from screens import account_inactivity as rule
from screens.models import AccountLifecycle, Source

DAY = datetime.timedelta(days=1)
EXEMPT_GROUP = "Exempt from inactivity removal"  # created by migration 0040
RULE = override_settings(ACCOUNT_INACTIVITY_DAYS=365, ACCOUNT_DELETION_GRACE_DAYS=90)


class _Accounts:
    def quieten_log(self):
        # Every action is logged at WARNING; assertLogs still sees them, as it
        # lowers the level itself for its duration.
        logger = logging.getLogger("screens.account_inactivity")
        self.addCleanup(logger.setLevel, logger.level)
        logger.setLevel(logging.ERROR)

    def make_user(self, username, idle_days, joined_days_ago=800, **fields):
        """A user last signed in `idle_days` ago (None: never)."""
        user = User.objects.create_user(username=username, password="pw", **fields)
        User.objects.filter(pk=user.pk).update(
            last_login=None if idle_days is None else self.now - idle_days * DAY,
            date_joined=self.now - joined_days_ago * DAY)
        return User.objects.get(pk=user.pk)

    @staticmethod
    def fetch(user):
        return User.objects.filter(pk=user.pk).first()

    @staticmethod
    def lifecycle(user):
        return AccountLifecycle.objects.filter(user_id=user.pk).first()

    def mark(self, user, days_ago):
        """As if the job deactivated `user` `days_ago` days ago."""
        User.objects.filter(pk=user.pk).update(is_active=False)
        AccountLifecycle.objects.update_or_create(
            user_id=user.pk, defaults={"deactivated_at": self.now - days_ago * DAY})


@RULE
class InactivityRuleTests(_Accounts, TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.quieten_log()
        # A recently active superuser keeps the last-superuser guard out of the
        # way unless a test is about it.
        self.admin = self.make_user("admin", 1, is_superuser=True, is_staff=True)

    def run_rule(self, **kwargs):
        return rule.apply(now=self.now, **kwargs)

    def test_recent_sign_in_is_left_alone(self):
        user = self.make_user("recent", 364)
        self.run_rule()
        self.assertTrue(self.fetch(user).is_active)
        self.assertIsNone(self.lifecycle(user))

    def test_idle_account_is_deactivated_and_marked(self):
        user = self.make_user("idle", 366)
        report = self.run_rule()
        self.assertFalse(self.fetch(user).is_active)
        self.assertEqual(self.lifecycle(user).deactivated_at, self.now)
        self.assertEqual([u.username for u in report.deactivated], ["idle"])

    def test_never_signed_in_counts_from_date_joined(self):
        fresh = self.make_user("fresh", None, joined_days_ago=10)
        stale = self.make_user("stale", None, joined_days_ago=400)
        self.run_rule()
        self.assertTrue(self.fetch(fresh).is_active)
        self.assertFalse(self.fetch(stale).is_active)

    def test_exempt_group_member_is_kept(self):
        user = self.make_user("breakglass", 1000)
        user.groups.add(Group.objects.get(name=EXEMPT_GROUP))
        self.run_rule()
        self.assertTrue(self.fetch(user).is_active)

    def test_superuser_is_not_exempt_by_holding_every_permission(self):
        # has_perm() is True for any superuser; the exemption must not be.
        stale_super = self.make_user("old-admin", 400, is_superuser=True, is_staff=True)
        self.run_rule()
        self.assertFalse(self.fetch(stale_super).is_active)

    def test_last_active_superuser_is_kept(self):
        User.objects.filter(pk=self.admin.pk).update(last_login=self.now - 400 * DAY)
        older = self.make_user("older-admin", 500, is_superuser=True, is_staff=True)
        with self.assertLogs("screens.account_inactivity", "WARNING") as logs:
            report = self.run_rule()
        self.assertTrue(self.fetch(self.admin).is_active)  # the more recent one
        self.assertFalse(self.fetch(older).is_active)
        self.assertEqual(report.kept_superuser.pk, self.admin.pk)
        self.assertIn("last active superuser", "\n".join(logs.output))

    def test_live_session_counts_as_activity(self):
        # A session re-saved by a team switch outlives the two-week age, so a
        # daily user may not have logged in for a year.
        user = self.make_user("daily", 400)
        session = SessionStore()
        session[SESSION_KEY] = str(user.pk)
        session.save()

        self.run_rule()
        self.assertTrue(self.fetch(user).is_active)
        self.assertEqual(self.lifecycle(user).last_seen, self.now)

    def test_already_inactive_account_starts_its_deletion_clock(self):
        user = self.make_user("offboarded", 400, is_active=False)
        self.run_rule()
        self.assertIsNotNone(self.fetch(user))
        self.assertEqual(self.lifecycle(user).deactivated_at, self.now)

    def test_deleted_once_grace_period_has_passed(self):
        due = self.make_user("due", 500)
        self.mark(due, 91)
        not_yet = self.make_user("not-yet", 500)
        self.mark(not_yet, 89)
        self.run_rule()
        self.assertIsNone(self.fetch(due))
        self.assertIsNotNone(self.fetch(not_yet))

    def test_exempting_a_deactivated_account_stops_its_deletion(self):
        user = self.make_user("rescued", 500)
        self.mark(user, 91)
        user.groups.add(Group.objects.get(name=EXEMPT_GROUP))
        self.run_rule()
        self.assertIsNotNone(self.fetch(user))

    def test_reactivating_restarts_the_clock(self):
        user = self.make_user("mistake", 400)
        self.run_rule()
        user = self.fetch(user)
        self.assertFalse(user.is_active)

        user.is_active = True
        user.save()  # as the admin change form does
        lifecycle = self.lifecycle(user)
        self.assertIsNone(lifecycle.deactivated_at)
        self.assertIsNotNone(lifecycle.last_seen)

        self.run_rule()
        self.assertTrue(self.fetch(user).is_active)

    def test_login_save_does_not_count_as_reactivation(self):
        user = self.make_user("ordinary", 10)
        user.last_login = self.now
        user.save(update_fields=["last_login"])
        self.assertIsNone(self.lifecycle(user))

    @override_settings(ACCOUNT_INACTIVITY_DAYS=0)
    def test_zero_switches_the_rule_off(self):
        user = self.make_user("idle", 5000)
        self.run_rule()
        self.assertTrue(self.fetch(user).is_active)

    def test_dry_run_changes_nothing(self):
        idle = self.make_user("idle", 400)
        due = self.make_user("due", 500)
        self.mark(due, 91)
        report = self.run_rule(dry_run=True)
        self.assertEqual([u.username for u in report.deactivated], ["idle"])
        self.assertEqual([u.username for u in report.deleted], ["due"])
        self.assertTrue(self.fetch(idle).is_active)
        self.assertIsNone(self.lifecycle(idle))
        self.assertIsNotNone(self.fetch(due))

    def test_deletion_keeps_the_users_content(self):
        user = self.make_user("author", 500)
        source = Source.objects.create(
            type=Source.IFRAME, name="their page", url="http://example.com",
            created_by=user)
        self.mark(user, 91)
        self.run_rule()
        source.refresh_from_db()
        self.assertIsNone(source.created_by)

    def test_command_dry_run_lists_and_changes_nothing(self):
        idle = self.make_user("idle", 400)
        out = StringIO()
        call_command("remove_inactive_accounts", "--dry-run", stdout=out)
        self.assertIn("Would deactivate: 1", out.getvalue())
        self.assertIn("idle", out.getvalue())
        self.assertTrue(self.fetch(idle).is_active)


@RULE
class InactivityAdminTests(_Accounts, TestCase):
    """The Users list and the dashboard are the only warning: there is no email."""

    def setUp(self):
        self.now = timezone.now()
        self.admin = self.make_user("admin", 1, is_superuser=True, is_staff=True)
        self.client.force_login(self.admin)
        self.deactivating = self.make_user("deactivating", 345)  # due in ~20 days
        self.deleting = self.make_user("deleting", 500)
        self.mark(self.deleting, 70)                             # due in ~20 days
        self.later = self.make_user("later", 300)
        self.exempt = self.make_user("exempt", 360)
        self.exempt.groups.add(Group.objects.get(name=EXEMPT_GROUP))

    def changelist(self, query=""):
        return self.client.get(reverse("admin:auth_user_changelist") + query)

    def test_upcoming_filter(self):
        resp = self.changelist("?inactivity=upcoming")
        users = {u.username for u in resp.context["cl"].result_list}
        self.assertEqual(users, {"deactivating", "deleting"})

    def test_exempt_filter(self):
        resp = self.changelist("?inactivity=exempt")
        users = {u.username for u in resp.context["cl"].result_list}
        self.assertEqual(users, {"exempt"})

    def test_column_names_the_next_event(self):
        resp = self.changelist()
        self.assertContains(resp, "Deactivates")
        self.assertContains(resp, "Deletes")
        self.assertContains(resp, "Exempt")

    @override_settings(ACCOUNT_INACTIVITY_DAYS=0)
    def test_column_hidden_when_rule_is_off(self):
        resp = self.changelist()
        self.assertNotIn("show_inactivity", resp.context["cl"].list_display)

    def test_dashboard_notice(self):
        resp = self.client.get(reverse("admin:index"))
        self.assertEqual(resp.context["accounts_upcoming"], 2)
        self.assertContains(resp, "2 accounts will be deactivated or deleted")
        self.assertContains(resp, "?inactivity=upcoming")
