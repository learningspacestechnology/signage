"""Accounts unused for `ACCOUNT_INACTIVITY_DAYS` are deactivated, then deleted
`ACCOUNT_DELETION_GRACE_DAYS` after that.

The single source of the rule: the nightly task, the management command, the
Users list and the dashboard all read it from here.

- **Activity** is the latest of `last_login`, `date_joined` (for an account that
  has never signed in) and `AccountLifecycle.last_seen`, which records what
  `last_login` misses: a live session, or an admin reactivating the account.
- **Live sessions count as activity.** A session is re-saved, and its expiry
  pushed back, whenever it changes — switching team does it — so someone using
  the admin daily can go far longer than the two-week session age without
  logging in again. Read from the database session table, so this relies on
  the default `SESSION_ENGINE`.
- **Exemption is an explicit grant** of `screens.exempt_from_inactivity_removal`,
  directly or through a group. Not `has_perm`, which is True for every
  superuser and so would exempt them all; superusers follow the rule like
  anyone else, except that the job never deactivates the last active one.
- **Deactivation is the undo window.** Ticking Active again restarts the clock
  (`AccountLifecycle.note_reactivation`). Deletion cascades to the user's admin
  history, so the WARNING log lines written here are the only record left.
"""

import datetime
import logging
from dataclasses import dataclass, field

from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import Permission, User
from django.contrib.sessions.models import Session
from django.db import transaction
from django.db.models import Exists, F, OuterRef, Q
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone

from screens.models import AccountLifecycle

logger = logging.getLogger(__name__)

EXEMPT_PERMISSION = "screens.exempt_from_inactivity_removal"

#: How far ahead the Users list filter and the dashboard notice look.
WARNING_DAYS = 30


def enabled():
    return int(settings.ACCOUNT_INACTIVITY_DAYS or 0) > 0


def _days(n):
    return datetime.timedelta(days=int(n))


def inactivity_period():
    return _days(settings.ACCOUNT_INACTIVITY_DAYS)


def grace_period():
    return _days(settings.ACCOUNT_DELETION_GRACE_DAYS)


def with_last_activity(queryset):
    """Annotate `last_activity` and `deactivated_at` onto a User queryset.

    Coalesce on both sides because Greatest returns NULL if any argument is
    NULL on MariaDB and SQLite; `date_joined` never is.
    """
    return queryset.annotate(
        last_activity=Greatest(
            Coalesce("last_login", "date_joined"),
            Coalesce("lifecycle__last_seen", "date_joined"),
        ),
        deactivated_at=F("lifecycle__deactivated_at"),
    )


def exempt_q():
    """Users holding the exemption explicitly, directly or through a group."""
    app_label, codename = EXEMPT_PERMISSION.split(".")
    perm = {"codename": codename, "content_type__app_label": app_label}
    return (Q(Exists(Permission.objects.filter(user=OuterRef("pk"), **perm)))
            | Q(Exists(Permission.objects.filter(group__user=OuterRef("pk"), **perm))))


def due_for_deactivation(now):
    """Unmarked accounts past the inactivity period, active or not.

    An account that is already inactive is included so that its deletion
    clock starts: deactivating it again changes nothing.
    """
    return (with_last_activity(User.objects.all())
            .filter(last_activity__lt=now - inactivity_period(),
                    deactivated_at__isnull=True)
            .exclude(exempt_q()))


def due_for_deletion(now):
    return (with_last_activity(User.objects.all())
            .filter(is_active=False,
                    deactivated_at__lt=now - grace_period())
            .exclude(exempt_q()))


def upcoming_q(now):
    """Accounts the job will deactivate or delete within WARNING_DAYS.

    For a queryset already passed through `with_last_activity`. Not exempt is
    left to the caller, which needs it anyway.
    """
    ahead = _days(WARNING_DAYS)
    deactivating = Q(is_active=True, deactivated_at__isnull=True,
                     last_activity__lt=now - inactivity_period() + ahead)
    deleting = Q(is_active=False,
                 deactivated_at__lt=now - grace_period() + ahead)
    return deactivating | deleting


def upcoming(now):
    """The dashboard notice's count: due within WARNING_DAYS, not exempt."""
    return (with_last_activity(User.objects.all())
            .filter(upcoming_q(now))
            .exclude(exempt_q()))


def next_event(user, now):
    """("Deactivates" | "Deletes", when) for a `with_last_activity` row, or None.

    `when` is never earlier than `now`: an overdue account goes at the next run.
    """
    if user.deactivated_at is not None:
        return "Deletes", max(user.deactivated_at + grace_period(), now)
    due = max(user.last_activity + inactivity_period(), now)
    if user.is_active:
        return "Deactivates", due
    return "Deletes", due + grace_period()


def _live_session_user_ids(now):
    ids = set()
    for session in Session.objects.filter(expire_date__gt=now).iterator():
        user_id = session.get_decoded().get(SESSION_KEY)
        if user_id is not None:
            ids.add(int(user_id))
    # A session can outlive its user, or belong to one already deactivated
    # (whose session no longer authenticates).
    return set(User.objects.filter(pk__in=ids, is_active=True)
               .values_list("pk", flat=True))


@dataclass
class Report:
    deactivated: list = field(default_factory=list)
    deleted: list = field(default_factory=list)
    #: The last active superuser, kept despite being due. None if no one was.
    kept_superuser: User = None


def apply(now=None, dry_run=False):
    """Run the rule once. With `dry_run`, report what would happen and write
    nothing."""
    report = Report()
    if not enabled():
        return report
    now = now or timezone.now()

    live = _live_session_user_ids(now)
    deactivate = [u for u in due_for_deactivation(now).order_by("last_activity")
                  if u.pk not in live]
    delete = list(due_for_deletion(now).order_by("deactivated_at"))

    # Never leave nobody able to manage users. Superusers are checked as a set:
    # if the whole active set is due, keep the one seen most recently.
    due_superusers = [u for u in deactivate if u.is_superuser and u.is_active]
    if due_superusers:
        others = (User.objects.filter(is_superuser=True, is_active=True)
                  .exclude(pk__in=[u.pk for u in due_superusers]))
        if not others.exists():
            report.kept_superuser = max(due_superusers, key=lambda u: u.last_activity)
            deactivate.remove(report.kept_superuser)
            logger.warning(
                "Inactive accounts: kept %s active despite no sign-in since %s, "
                "as the last active superuser.",
                report.kept_superuser.username, report.kept_superuser.last_activity)

    report.deactivated = deactivate
    report.deleted = delete
    if dry_run:
        return report

    with transaction.atomic():
        for pk in live:
            AccountLifecycle.objects.update_or_create(
                user_id=pk, defaults={"last_seen": now})
        # A queryset update, so note_reactivation does not see it — it only
        # acts on a False -> True change anyway.
        User.objects.filter(pk__in=[u.pk for u in deactivate]).update(is_active=False)
        for user in deactivate:
            AccountLifecycle.objects.update_or_create(
                user_id=user.pk, defaults={"deactivated_at": now})
        User.objects.filter(pk__in=[u.pk for u in delete]).delete()

    for user in deactivate:
        # `user.is_active` is the value read before the update above.
        action = "deactivated" if user.is_active else "started the deletion clock for"
        logger.warning("Inactive accounts: %s %s (no sign-in since %s).",
                       action, user.username, user.last_activity)
    for user in delete:
        logger.warning("Inactive accounts: deleted %s (deactivated %s, no sign-in since %s).",
                       user.username, user.deactivated_at, user.last_activity)
    return report
