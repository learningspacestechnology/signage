from django.conf import settings
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User, Group
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.urls import path
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextInputWidget

from advertising.middleware import (
    ALL_TEAMS,
    ALL_TEAMS_SESSION_VALUE,
    SESSION_KEY as ACTIVE_TEAM_SESSION_KEY,
)
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
    return get_o365_admin_urls() + custom + _original_admin_get_urls()


admin.site.get_urls = _patched_admin_get_urls


def team_switcher_dropdown(request):
    """Items for Unfold's SITE_DROPDOWN listing teams the user can switch to."""
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

def dashboard_callback(_request, context):
    context["app_list"] = [
        app for app in context.get("app_list", [])
        if app["app_label"] in ("screens")
    ]
    return context


admin.site.unregister(User)
admin.site.unregister(Group)
admin.site.unregister(PeriodicTask)
admin.site.unregister(IntervalSchedule)
admin.site.unregister(CrontabSchedule)
admin.site.unregister(SolarSchedule)
admin.site.unregister(ClockedSchedule)
admin.site.unregister(TaskResult)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


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
