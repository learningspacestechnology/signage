import json

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User, Group, Permission
from django.db.models import Count
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.templatetags.static import static
from django.urls import path, reverse
from django.views.decorators.http import require_POST
from unfold.admin import ModelAdmin
from unfold.decorators import display
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
# Pure data, no models — safe to import at module scope, unlike screens.models
# (which the functions below import lazily, as the rest of this file does).
from screens.accents import ACCENTS, DEFAULT_ACCENT, light_ramp, swatches

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


def accent_slug(request):
    """The accent palette slug for this request's user.

    Cached on the request because two Unfold callables (`accent_palette` and
    `accent_stylesheet`) both need it on every admin render, and this would
    otherwise be two queries per page instead of one.
    """
    from screens.models import UserPreference

    cached = getattr(request, '_accent_slug', None)
    if cached is not None:
        return cached

    slug = DEFAULT_ACCENT
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        slug = (
            UserPreference.objects
            .filter(user=user)
            .values_list('accent', flat=True)
            .first()
        ) or DEFAULT_ACCENT

    request._accent_slug = slug
    return slug


def accent_palette(request):
    """Unfold COLORS["primary"] callable: the user's light-mode ramp.

    Returns a fresh dict every call — Unfold's `_get_colors` rewrites the dict
    it is handed in place, so sharing the registry's would let one request
    permanently recolour the admin for everyone else.
    """
    return light_ramp(accent_slug(request))


def accent_stylesheet(request):
    """Unfold STYLES callable: the user's dark-mode override stylesheet.

    Unfold uses --color-primary-500 for text on white *and* on near-black, so
    the single :root ramp above cannot be right in both themes. This sheet
    re-declares the three dark-background slots under `html.dark`, which
    out-ranks :root on specificity. See screens/accents.py.
    """
    return static(f'screens/css/accent/{accent_slug(request)}.css')


def accent_picker_items(request):
    """Palettes for the accent picker in the sidebar user menu.

    Consumed by the `accent_picker_items` tag in
    `screens/templatetags/accent_picker.py`, rendered by this project's
    `templates/unfold/helpers/accent_switch.html`.
    """
    if not (request.user.is_authenticated and request.user.is_staff):
        return []

    active = accent_slug(request)
    items = []
    for slug, palette in ACCENTS.items():
        swatch_light, swatch_dark = swatches(slug)
        items.append({
            "slug": slug,
            "label": palette["label"],
            "swatch_light": swatch_light,
            "swatch_dark": swatch_dark,
            "is_active": slug == active,
        })
    return items


@require_POST
@user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url='/admin/login/')
def set_accent_view(request):
    """Store the user's accent choice. Slug arrives in the POST body.

    POST rather than the GET link `set_active_team_view` uses: this writes a
    database row, so a plain link would be CSRF-able. The slug is in the body
    rather than the URL so all nine swatches can share one form and one CSRF
    token inside the menu.
    """
    from screens.models import UserPreference

    slug = request.POST.get('accent')
    if slug not in ACCENTS:
        return HttpResponseBadRequest("Unknown accent colour.")

    UserPreference.objects.update_or_create(
        user=request.user,
        defaults={'accent': slug},
    )

    next_url = request.META.get('HTTP_REFERER') or '/admin/'
    return HttpResponseRedirect(next_url)


def _patched_admin_get_urls():
    custom = [
        path(
            'set-active-team/<str:team_ref>/',
            set_active_team_view,
            name='set_active_team',
        ),
        path(
            'set-accent/',
            set_accent_view,
            name='set_accent',
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
    from screens.models import (
        Playlist, Schedule, Screen, ScreenStatus, Source, StatusReason)
    from screens.team_scope import scope_to_active_team

    screens_qs = scope_to_active_team(Screen.objects.all(), request)
    playlists_qs = scope_to_active_team(Playlist.objects.all(), request)
    schedules_qs = scope_to_active_team(Schedule.objects.all(), request)
    sources_qs = scope_to_active_team(Source.objects.all(), request)

    # Counted off the same with_status() annotation the changelist badge and
    # filter use, so the doughnut cannot disagree with them. This used to
    # re-hardcode `now - 1 minute`, which was the only copy of the online cutoff
    # living outside Screen.
    by_status = {
        row["derived_status"]: row["n"]
        for row in (screens_qs.with_status()
                    .values("derived_status")
                    # distinct=True because team scoping joins the teams M2M;
                    # today's single-team filter cannot duplicate a row, but a
                    # plain Count would silently start double-counting if that
                    # ever became a teams__in.
                    .annotate(n=Count("id", distinct=True)))
    }
    screens_online = by_status.get(ScreenStatus.ONLINE, 0)
    screens_attention = by_status.get(ScreenStatus.ATTENTION, 0)
    screens_offline = by_status.get(ScreenStatus.OFFLINE, 0)
    screens_total = screens_online + screens_attention + screens_offline

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

    # Amber first, then red — see ScreenQuerySet.needing_attention(). The
    # "since" figure comes from recorded history and lags the live status by up
    # to one check_screens cycle, so it is only used while the two agree;
    # otherwise the heartbeat, which is always current, is shown instead.
    attention_screens = [
        {
            "name": s.name or f"Screen #{s.pk}",
            "status": s.derived_status,
            # From the annotation, not status_reason_label(), so the word and
            # the badge come from the same evaluation of the tiers.
            "reason": StatusReason(s.derived_reason).label if s.derived_reason else "",
            "since": s.status_since if s.recorded_status == s.derived_status else None,
            "last_seen": s.last_seen,
            "url": reverse("admin:screens_screen_change", args=[s.pk]),
        }
        for s in screens_qs.needing_attention()[:5]
    ]

    context.update({
        "title": "Overview Dashboard",  # replaces the default "Site administration"
        "app_list": [],  # dashboard-only layout — no default model list

        "screens_total": screens_total,
        "screens_online": screens_online,
        "screens_attention": screens_attention,
        "screens_offline": screens_offline,
        "screens_url": reverse("admin:screens_screen_changelist"),
        "screens_chart_data": _doughnut_data(
            ["Online", "Needs attention", "Offline"],
            [screens_online, screens_attention, screens_offline],
            ["#22c55e", "#f59e0b", "#ef4444"],
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

        "attention_screens": attention_screens,

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


class TeamListFilter(admin.RelatedFieldListFilter):
    """Team filter for the Users list, with the "no team" option spelled out.

    The stock label for that option is the changelist's empty value ("-"), and
    it is the case most worth finding: a staff user with no team sees nothing at
    all until one is assigned.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = "team"
        self.empty_value_display = "No team"


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = PreprovisionUserCreationForm
    change_password_form = AdminPasswordChangeForm
    autocomplete_fields = ("groups", "user_permissions")
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "show_teams",
        "is_staff",
    )
    # `teams` is the reverse side of Team.members, so the filter also offers the
    # "no team" case (see TeamListFilter).
    list_filter = BaseUserAdmin.list_filter + (("teams", TeamListFilter),)
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

    def get_queryset(self, request):
        # show_teams walks every row's teams; without this the changelist runs a
        # query per user.
        return super().get_queryset(request).prefetch_related("teams")

    @display(description="Teams")
    def show_teams(self, obj):
        # Iterating the prefetched manager, not values_list, so the prefetch above
        # is actually used.
        return ", ".join(team.name for team in obj.teams.all()) or "—"

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
