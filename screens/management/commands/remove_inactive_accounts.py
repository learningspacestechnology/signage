"""Run the inactive-account rule now, or preview it.

    uv run python manage.py remove_inactive_accounts --dry-run

The nightly task `screens.tasks.remove_inactive_accounts` does the same thing
without `--dry-run`. Preview before a first deploy, or after changing
ACCOUNT_INACTIVITY_DAYS: the rule acts on everything already past it at once.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from screens import account_inactivity


class Command(BaseCommand):
    help = ("Deactivate accounts with no sign-in for ACCOUNT_INACTIVITY_DAYS, and "
            "delete those deactivated more than ACCOUNT_DELETION_GRACE_DAYS ago.")

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="List what would happen without changing anything.")

    def handle(self, *args, dry_run=False, **options):
        if not account_inactivity.enabled():
            self.stdout.write("ACCOUNT_INACTIVITY_DAYS is 0: the rule is off.")
            return

        report = account_inactivity.apply(now=timezone.now(), dry_run=dry_run)
        would = "Would" if dry_run else "Did"

        def when(dt):
            return timezone.localtime(dt).strftime("%Y-%m-%d") if dt else "never"

        newly = [u for u in report.deactivated if u.is_active]
        already = [u for u in report.deactivated if not u.is_active]
        sections = (
            (f"{would} deactivate", newly, "last active"),
            (f"{would} start the deletion clock for (already inactive)", already,
             "last active"),
            (f"{would} delete", report.deleted, "deactivated"),
        )
        for title, users, label in sections:
            self.stdout.write(f"{title}: {len(users)}")
            for user in users:
                date = user.deactivated_at if label == "deactivated" else user.last_activity
                flag = " [superuser]" if user.is_superuser else ""
                self.stdout.write(f"  {user.username}{flag} — {label} {when(date)}")

        if report.kept_superuser is not None:
            self.stdout.write(self.style.WARNING(
                f"Kept {report.kept_superuser.username} active: it is the last "
                "active superuser."))
        if dry_run:
            self.stdout.write(
                "Nothing was changed. Add accounts that must stay to the "
                '"Exempt from inactivity removal" group.')
