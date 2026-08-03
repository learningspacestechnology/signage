import json
from datetime import timedelta

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User, Group, Permission
from django.db.models import Count
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextInputWidget

from advertising.forms import PreprovisionUserCreationForm

from advertising.middleware import (
    ALL_TEAMS,
    ALL_TEAMS_SESSION_VALUE,
    SESSION_KEY as ACTIVE_TEAM_SESSION_KEY,
)
from helpdocs.admin_links import attach_help_links
from helpdocs.urls import get_help_admin_urls
from room_schedules.admin import get_o365_admin_urls

_original_admin_get_urls = admin.site.get_urls


@user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url='/admin/login/')
def set_active_team_view(request, team_ref):
    """Update the session's active team. `team_ref` is a team PK or 'all'."""
    from screens.models import Team

    if team_ref == 'all':
        if not request.user.is_superuser:
            return HttpResponseBadRequest("Only superusers can use the all-teams view.")
        request.session[ACTIVE_TEAM_SESSION_KEY] = ALL_TEAMS_SESSION_VALUE
    else:
        try:
            team_pk = int(team_ref)
        except (TypeError, ValueError):
            return HttpResponseBadRequest("Invalid team reference.")
        if request.user.is_superuser:
            qs = Team.objects.filter(pk=team_pk)
        else:
            qs = request.user.teams.filter(pk=team_pk)
        if not qs.exists():
            return HttpResponseBadRequest("Team not found or not accessible.")
        request.session[ACTIVE_TEAM_SESSION_KEY] = team_pk

    next_url = request.META.get('HTTP_REFERER') or '/admin/'
    return HttpResponseRedirect(next_url)


def _patched_admin_get_urls():
    custom = [
        path(
            'set-active-team/<str:team_ref>/',
            set_active_team_view,
            name='set_active_team',
        ),
    ]
    return (
        get_help_admin_urls()
        + get_o365_admin_urls()
        + custom
        + _original_admin_get_urls()
    )


admin.site.get_urls = _patched_admin_get_urls


def team_switcher_dropdown(request):
    """Teams the user can switch to, for the header's team picker.

    Consumed by the `team_switcher_items` tag in
    `screens/templatetags/team_switcher.py`, which the project's override of
    `unfold/helpers/userlinks.html` renders. Not Unfold's `SITE_DROPDOWN` — that
    setting is not configured.
    """
    if not (request.user.is_authenticated and request.user.is_staff):
        return []

    from django.urls import reverse

    active = getattr(request, 'active_team', None)
    items = []

    if request.user.is_superuser:
        items.append({
            "icon": "check" if active is ALL_TEAMS else "groups",
            "title": "All teams",
            "link": reverse('admin:set_active_team', args=['all']),
        })

    teams_qs = (
        __import__('screens.models', fromlist=['Team']).Team.objects.all()
        if request.user.is_superuser
        else request.user.teams.all()
    ).order_by('name')

    active_pk = active.pk if (active and active is not ALL_TEAMS) else None
    for team in teams_qs:
        items.append({
            "icon": "check" if team.pk == active_pk else "group",
            "title": team.name,
            "link": reverse('admin:set_active_team', args=[team.pk]),
        })
    return items


def active_team_environment(request):
    """Unfold ENVIRONMENT callable: top-of-page label showing the active team."""
    active = getattr(request, 'active_team', None)
    if active is None:
        return None
    if active is ALL_TEAMS:
        return ["All teams", "danger"]
    return [f"Team: {active.name}", "info"]


def site_name(_request):
    """Unfold SITE_TITLE/SITE_HEADER callable: resolved at render time so any
    settings layer overriding ADMIN_SITE_NAME (dev settings.py, deploy
    settings.py) flows through without rebuilding the UNFOLD dict."""
    return settings.ADMIN_SITE_NAME

from django_celery_beat.models import (
    ClockedSchedule,
    CrontabSchedule,
    IntervalSchedule,
    PeriodicTask,
    SolarSchedule,
)
from django_celery_beat.admin import ClockedScheduleAdmin as BaseClockedScheduleAdmin
from django_celery_beat.admin import CrontabScheduleAdmin as BaseCrontabScheduleAdmin
from django_celery_beat.admin import PeriodicTaskAdmin as BasePeriodicTaskAdmin
from django_celery_beat.admin import PeriodicTaskForm, TaskSelectWidget
from django_celery_results.admin import TaskResultAdmin
from django_celery_results.models import TaskResult

def _doughnut_data(labels, data, colors):
    """JSON payload for Unfold's bundled chart.js (`data-value` on a `.chart`
    canvas). Template autoescaping turns the quotes into entities the browser
    decodes back — same as Unfold's own chart components."""
    return json.dumps({
        "labels": labels,
        "datasets": [{"data": data, "backgroundColor": colors, "borderWidth": 0}],
    })


def _getting_started_steps():
    """First-run path for the dashboard's Getting started panel.

    Slugs must exist in helpdocs.registry; check_help_docs verifies that.
    """
    steps = (
        ("login", "Sign in and find your way around", "getting-started"),
        ("groups", "Understand teams and what you can see", "teams"),
        ("perm_media", "Upload your content", "content"),
        ("queue_play_next", "Build a playlist", "playlists"),
        ("calendar_today", "Decide when it plays", "schedules"),
        ("monitor", "Point a screen at it", "screens"),
    )
    return [
        {
            "icon": icon,
            "label": label,
            "url": reverse(
                "admin:help_page",
                kwargs={"audience": "users", "slug": slug},
            ),
        }
        for icon, label, slug in steps
    ]


def dashboard_callback(request, context):
    """Populate the admin index with a team-scoped dashboard.

    Every count respects the active team via ``scope_to_active_team`` — the same
    helper the changelists use — so users only ever see their own team's totals
    (superusers in ALL_TEAMS mode see global totals)."""
    from screens.models import Playlist, Schedule, Screen, Source
    from screens.team_scope import scope_to_active_team

    screens_qs = scope_to_active_team(Screen.objects.all(), request)
    playlists_qs = scope_to_active_team(Playlist.objects.all(), request)
    schedules_qs = scope_to_active_team(Schedule.objects.all(), request)
    sources_qs = scope_to_active_team(Source.objects.all(), request)

    # "Online" mirrors Screen.online(): last_seen within the last minute.
    online_cutoff = timezone.now() - timedelta(minutes=1)
    screens_total = screens_qs.count()
    screens_online = screens_qs.filter(last_seen__gte=online_cutoff).count()
    screens_offline = screens_total - screens_online

    # Content broken down by type (Image / Video / Website).
    type_colors = {
        Source.IMAGE: "#0ea5e9",   # sky
        Source.VIDEO: "#8b5cf6",   # violet
        Source.IFRAME: "#f59e0b",  # amber
    }
    by_type = {row["type"]: row["n"]
               for row in sources_qs.values("type").annotate(n=Count("id"))}
    content_by_type = [
        {"label": label, "count": by_type.get(key, 0), "color": type_colors[key]}
        for key, label in Source.types
    ]

    # last_seen has auto_now_add, so it is never null; "< cutoff" == not online.
    offline_screens = [
        {
            "name": s.name or f"Screen #{s.pk}",
            "last_seen": s.last_seen,
            "url": reverse("admin:screens_screen_change", args=[s.pk]),
        }
        for s in screens_qs.filter(last_seen__lt=online_cutoff).order_by("last_seen")[:5]
    ]

    context.update({
        "title": "Overview Dashboard",  # replaces the default "Site administration"
        "app_list": [],  # dashboard-only layout — no default model list

        "screens_total": screens_total,
        "screens_online": screens_online,
        "screens_offline": screens_offline,
        "screens_url": reverse("admin:screens_screen_changelist"),
        "screens_chart_data": _doughnut_data(
            ["Online", "Offline"], [screens_online, screens_offline],
            ["#22c55e", "#ef4444"],
        ),

        "playlists_count": playlists_qs.count(),
        "playlists_url": reverse("admin:screens_playlist_changelist"),
        "schedules_count": schedules_qs.count(),
        "schedules_url": reverse("admin:screens_schedule_changelist"),
        "content_count": sources_qs.count(),
        "content_url": reverse("admin:screens_source_changelist"),

        "content_by_type": content_by_type,
        "content_type_chart_data": _doughnut_data(
            [c["label"] for c in content_by_type],
            [c["count"] for c in content_by_type],
            [c["color"] for c in content_by_type],
        ),

        "offline_screens": offline_screens,

        "can_add_source": request.user.has_perm("screens.add_source"),
        "can_add_playlist": request.user.has_perm("screens.add_playlist"),
        "bulk_upload_url": reverse("admin:screens_source_bulk_create"),
        "add_content_url": reverse("admin:screens_source_add"),
        "add_playlist_url": reverse("admin:screens_playlist_add"),

        # Getting-started panel. The step links go straight to the help pages
        # rather than the admin screens, because a first-time user needs the
        # explanation before the form.
        "help_index_url": reverse("admin:help_index"),
        "help_steps": _getting_started_steps(),
    })
    return context


admin.site.unregister(User)
admin.site.unregister(Group)
admin.site.unregister(PeriodicTask)
admin.site.unregister(IntervalSchedule)
admin.site.unregister(CrontabSchedule)
admin.site.unregister(SolarSchedule)
admin.site.unregister(ClockedSchedule)
admin.site.unregister(TaskResult)


@admin.register(Permission)
class PermissionAdmin(ModelAdmin):
    """Registered only so `autocomplete_fields` can search permissions.

    With ~140 permissions the stock `filter_horizontal` picker is a wall of
    scrolling; autocomplete needs the related model to have a registered admin
    with `search_fields`. This admin is read-only and deliberately kept out of
    the sidebar (the UNFOLD nav is an explicit list, so it never appears).
    """

    search_fields = (
        "name",
        "codename",
        "content_type__app_label",
        "content_type__model",
    )
    def has_view_permission(self, request, obj=None):
        # Django gates the autocomplete endpoint on this, so mirror "may edit
        # groups or users" rather than requiring a separate auth.view_permission
        # grant on every group-editing user.
        return request.user.has_perm("auth.change_group") or request.user.has_perm(
            "auth.change_user"
        )

    def has_module_permission(self, request):
        # Keep it off the admin index; it exists purely to back autocomplete.
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = PreprovisionUserCreationForm
    change_password_form = AdminPasswordChangeForm
    autocomplete_fields = ("groups", "user_permissions")
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "description": (
                    "Create a user who signs in with Microsoft/Entra. Enter their "
                    "sign-in address as the email; leave the password blank for "
                    "SSO-only accounts."
                ),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "is_staff",
                    "teams",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        # Only superusers manage team membership (see CLAUDE.md); hide the field
        # from everyone else on the add form.
        if obj is None and not request.user.is_superuser:
            fieldsets = [
                (
                    name,
                    {**opts, "fields": tuple(f for f in opts["fields"] if f != "teams")},
                )
                for name, opts in fieldsets
            ]
        return fieldsets

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # `teams` only exists on the add form; a no-op on the change page.
        # Gate on is_superuser so a crafted POST can't grant team access even
        # though get_fieldsets already hides the field from non-superusers.
        teams = form.cleaned_data.get("teams")
        if teams and request.user.is_superuser:
            from screens.models import TeamMembership

            for team in teams:
                TeamMembership.objects.get_or_create(user=form.instance, team=team)


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    autocomplete_fields = ("permissions",)


class UnfoldTaskSelectWidget(UnfoldAdminSelectWidget, TaskSelectWidget):
    pass


class UnfoldPeriodicTaskForm(PeriodicTaskForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["task"].widget = UnfoldAdminTextInputWidget()
        self.fields["regtask"].widget = UnfoldTaskSelectWidget()


@admin.register(PeriodicTask)
class PeriodicTaskAdmin(BasePeriodicTaskAdmin, ModelAdmin):
    form = UnfoldPeriodicTaskForm


@admin.register(IntervalSchedule)
class IntervalScheduleAdmin(ModelAdmin):
    pass


@admin.register(CrontabSchedule)
class CrontabScheduleAdmin(BaseCrontabScheduleAdmin, ModelAdmin):
    pass


@admin.register(SolarSchedule)
class SolarScheduleAdmin(ModelAdmin):
    pass


@admin.register(ClockedSchedule)
class ClockedScheduleAdmin(BaseClockedScheduleAdmin, ModelAdmin):
    pass


@admin.register(TaskResult)
class TaskResultAdmin(TaskResultAdmin, ModelAdmin):
    pass


# Must be the last statement in this module: it walks admin.site's registry, and
# every unregister/register above would otherwise drop the attachment. This module
# is imported from advertising/urls.py, i.e. after admin autodiscover has loaded
# screens.admin and room_schedules.admin, so the registry is complete by now.
attach_help_links()
