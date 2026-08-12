from admin_ordering.admin import OrderableAdmin
from django import forms
from django.conf import settings
from django.urls import re_path
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.template.response import TemplateResponse
from unfold.admin import ModelAdmin, TabularInline, StackedInline
from unfold.decorators import display

from advertising.middleware import ALL_TEAMS
from screens.forms import SourceBulkCreateForm, PlaylistAssigningSourceForm
from screens.models import (
    Playlist,
    PlaylistEntry,
    Schedule,
    ScheduleRule,
    Screen,
    Source,
    Team,
    TeamMembership,
)
from screens.team_scope import scope_to_active_team, scope_to_user_teams


class TeamScopedAdminMixin:
    """Filter querysets, FK choices, the teams M2M widget, and auto-attach the active team on save."""

    def get_queryset(self, request):
        return scope_to_active_team(super().get_queryset(request), request)

    def delete_queryset(self, request, queryset):
        """Re-resolve by primary key before deleting.

        ``scope_to_active_team`` returns a ``.distinct()`` queryset on both of its
        branches, and Django refuses ``.delete()`` on one (``TypeError``). That
        only bites the changelist's ``delete_selected`` action, which is the sole
        path calling ``queryset.delete()`` — single-object deletes go through
        ``obj.delete()`` and were never affected. Materialising the pks keeps the
        distinct flag out of the delete query entirely.
        """
        pks = list(queryset.values_list('pk', flat=True))
        super().delete_queryset(
            request, self.model._default_manager.filter(pk__in=pks),
        )

    def get_exclude(self, request, obj=None):
        excluded = list(super().get_exclude(request, obj) or [])
        if not request.user.is_superuser and 'teams' not in excluded:
            excluded.append('teams')
        return excluded

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            return fieldsets
        cleaned = []
        for name, opts in fieldsets:
            fields = [f for f in opts.get('fields', []) if f != 'teams']
            cleaned.append((name, {**opts, 'fields': fields}))
        return cleaned

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == 'teams':
            if request.user.is_superuser:
                kwargs['queryset'] = Team.objects.all()
                kwargs['required'] = request.active_team is ALL_TEAMS
        elif db_field.name == 'playlists':
            kwargs['queryset'] = scope_to_user_teams(Playlist.objects.all(), request)
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name in ('interspersed_playlist', 'default_playlist', 'schedule'):
            kwargs['queryset'] = scope_to_active_team(
                db_field.related_model.objects.all(), request,
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        active = getattr(request, 'active_team', None)
        if active is None or active is ALL_TEAMS:
            return
        if not obj.teams.filter(pk=active.pk).exists():
            obj.teams.add(active)


class HideChangeFormDeleteMixin:
    """Hide the Delete button on the change form (it confuses operators).

    Delete remains available via the changelist's bulk action and the object's
    delete confirmation page; only the submit-row button is hidden, by setting
    ``show_delete`` to False (read by Django's ``submit_row`` tag).
    """

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = {**(extra_context or {}), 'show_delete': False}
        return super().change_view(request, object_id, form_url, extra_context=extra_context)


class PlaylistEntryInline(OrderableAdmin, TabularInline):
    model = PlaylistEntry
    ordering_field = 'number'
    verbose_name_plural = "Content (plays in number order, lowest first)"
    extra = 0
    fields = ('number', 'thumbnail', 'source', 'duration')
    readonly_fields = ('thumbnail',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'source':
            kwargs['queryset'] = scope_to_user_teams(Source.objects.all(), request)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class PlaylistParentsInlineForm(forms.ModelForm):
    def clean(self):
        cleaned = super().clean()
        request = getattr(self, '_request', None)
        super_list = cleaned.get('super_list')
        if request is None or super_list is None or request.user.is_superuser:
            return cleaned
        if not super_list.teams.filter(pk__in=request.user.teams.values_list('pk', flat=True)).exists():
            raise ValidationError(
                "You can only inherit from a playlist owned by one of your own teams.",
            )
        return cleaned


class PlaylistParentsInline(TabularInline):
    model = Playlist.parents.through
    form = PlaylistParentsInlineForm
    fk_name = "inheriting_list"
    verbose_name_plural = "Playlists to inherit from"
    verbose_name = "Parent List"
    extra = 0

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'super_list':
            kwargs['queryset'] = scope_to_user_teams(Playlist.objects.all(), request)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        original_init = formset.form.__init__

        def patched_init(inner_self, *args, **inner_kwargs):
            original_init(inner_self, *args, **inner_kwargs)
            inner_self._request = request

        formset.form.__init__ = patched_init
        return formset


@admin.register(Playlist)
class PlaylistDisplay(HideChangeFormDeleteMixin, TeamScopedAdminMixin, ModelAdmin):
    list_display = ('name', 'show_source_count', 'show_teams', 'last_updated')
    search_fields = ('name', 'description')
    readonly_fields = ('last_updated',)
    fieldsets = [
        (None, {'fields': ['name', 'description', 'default_duration', 'last_updated', 'teams']}),
        ('Interspersed content', {
            'fields': ['interspersed_playlist', 'interspersed_rate'],
            'description': "Mix another playlist — typically a logo or standing message — "
                           "in between this playlist's own entries.",
        }),
    ]
    inlines = [PlaylistParentsInline, PlaylistEntryInline]

    @display(description="Content")
    def show_source_count(self, obj):
        return obj.playlistentry_set.count()

    @display(description="Teams")
    def show_teams(self, obj):
        return ", ".join(obj.teams.values_list('name', flat=True))

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            re_path(r'^tree/$', self.admin_site.admin_view(self.playlist_tree_view), name='screens_playlist_tree'),
        ]
        return my_urls + urls

    def playlist_tree_view(self, request):
        context = self.admin_site.each_context(request)
        context['title'] = 'Playlist Inheritance'
        context['is_fullwidth'] = "1"
        return TemplateResponse(request, 'admin/screens/playlist_tree.html', context)


class ScheduleRuleInline(StackedInline):
    model = ScheduleRule
    extra = 0
    fieldsets = (
        (None, {
            'description': (
                "Each rule points a time window at a playlist. When two rules overlap, the one with the "
                "LOWEST priority number wins. If no rule matches right now, the schedule's default playlist is shown."
            ),
            'fields': ('playlist', 'starts', 'occurrences', 'start_time', 'end_time', 'priority'),
        }),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'playlist':
            kwargs['queryset'] = scope_to_active_team(Playlist.objects.all(), request)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    class Media:
        # django-recurrence's init script observes #container for new inline rows,
        # but Unfold doesn't render that element. Re-init on Django's formset:added.
        js = ('screens/js/recurrence_unfold_init.js',)
        css = {'all': ('screens/css/recurrence_unfold.css',)}


@admin.register(Schedule)
class ScheduleDisplay(HideChangeFormDeleteMixin, TeamScopedAdminMixin, ModelAdmin):
    # is_default is intentionally absent from list_display/list_filter/fieldsets: the
    # field is still live on the model, just not editable here. Re-add to re-expose.
    list_display = ('name', 'default_playlist', 'show_teams')
    search_fields = ('name', 'description')
    list_select_related = ('default_playlist',)
    fieldsets = [
        (None, {'fields': ['name', 'description', 'default_playlist', 'teams']}),
    ]
    inlines = [ScheduleRuleInline]

    @display(description="Teams")
    def show_teams(self, obj):
        return ", ".join(obj.teams.values_list('name', flat=True))


class PlaylistListFilter(admin.SimpleListFilter):
    title = "In Playlist"
    parameter_name = "playlist"

    def lookups(self, request, model_admin):
        return scope_to_active_team(Playlist.objects.all(), request).values_list("id", "name")

    def queryset(self, request, queryset):
        if self.value() is None:
            return queryset
        return queryset.filter(playlistentry__playlist__id=self.value())


@admin.register(Source)
class SourceDisplay(HideChangeFormDeleteMixin, TeamScopedAdminMixin, ModelAdmin):
    readonly_fields = ('image_preview',)
    list_display = ('thumbnail', 'name', 'show_type', 'resolution', 'created_by', 'playlist_names', 'show_teams', 'created_at', 'valid_from', 'expires_at')
    # Without this the link to the change form lands on the first column — the
    # thumbnail — which reads as decoration, not as the way in. Link the name.
    list_display_links = ('name',)
    list_filter = (PlaylistListFilter, 'type')
    search_fields = ('name',)
    date_hierarchy = 'created_at'

    @display(description="Preview")
    def thumbnail(self, obj):
        from django.template.loader import get_template
        return get_template("screens/source_thumbnail.html").render({"source": obj})

    @display(description="Type", label={
        "Image": "success",
        "Video": "warning",
        "Website": "info",
    })
    def show_type(self, obj):
        return obj.get_type_display()

    @display(description="Teams")
    def show_teams(self, obj):
        return ", ".join(obj.teams.values_list('name', flat=True))

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            re_path(r'^bulk_create/$', self.bulk_create_view, name='screens_source_bulk_create'),
        ]
        return my_urls + urls

    def bulk_create_view(self, request):
        request.bulk_create = True
        return super().changeform_view(request)

    def get_form(self, request, obj=None, **kwargs):
        if obj is None and hasattr(request, "bulk_create") and request.bulk_create:  # TODO and bulk create permission
            kwargs['form'] = SourceBulkCreateForm
            self.exclude = ("file", "name")
        else:
            kwargs["form"] = PlaylistAssigningSourceForm
            self.exclude = ()
        form_class = super().get_form(request, obj, **kwargs)
        if 'playlists' in form_class.base_fields:
            form_class.base_fields['playlists'].queryset = scope_to_user_teams(
                Playlist.objects.all(), request,
            )
        return form_class

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        form.save(commit=True)

    class Media:
        js = (
            "admin/js/jquery.init.js",
            'screens/js/source_form.js',
        )


TICKER_GATE_FIELDS = ('ticker_enabled', 'ticker_layout')
TICKER_TEXT_FIELDS = (
    'ticker_text', 'ticker_style_preset',
    'ticker_font_size_px', 'ticker_font_color',
    'ticker_background_color', 'ticker_background_opacity',
    'ticker_scroll_speed_px_sec',
)
TICKER_GATE_PERM = 'screens.change_ticker_settings'
TICKER_TEXT_PERM = 'screens.change_ticker_text'

INTERSPERSED_FIELDS = ('interspersed_playlist', 'interspersed_rate')
INTERSPERSED_UNAVAILABLE_FIELD = 'interspersed_unavailable'


@admin.register(Screen)
class ScreenAdmin(TeamScopedAdminMixin, ModelAdmin):
    readonly_fields = ('screen_preview', INTERSPERSED_UNAVAILABLE_FIELD)
    list_display = ('name', 'ip', 'show_online', 'last_seen', 'schedule', 'show_teams')
    search_fields = ('name', 'ip')
    list_filter = ('schedule',)
    list_select_related = ('schedule',)
    fieldsets = (
        (None, {
            'fields': ('name', 'schedule', 'ip', 'teams', 'screen_preview'),
        }),
        ('Interspersed content', {
            'fields': INTERSPERSED_FIELDS,
            'description': "Mix a playlist — typically an event schedule or room sign — "
                           "into whatever this screen is showing.",
        }),
        ('Ticker tape', {
            'classes': ('collapse',),
            'fields': TICKER_GATE_FIELDS + TICKER_TEXT_FIELDS,
        }),
    )

    def _interspersed_blocked_by_ticker(self, obj):
        """Whether this screen's own interspersed content could play at all.

        It cannot while the ticker is on: the ticker wrapper iframes
        /playlist/<id>, which carries no screen context, so the screen's stream
        never reaches the player. Hide the fields rather than let an operator
        configure something that will be silently ignored. See KNOWN_ISSUES.md.

        Keyed on ticker_enabled rather than has_ticker() — the latter is the
        precise condition but would make the fields appear and disappear as the
        operator types ticker text.
        """
        return obj is not None and obj.ticker_enabled

    def _hidden_fields(self, request, obj=None):
        """Fields this user, on this screen, may not see.

        Both ticker tiers are grantable permissions, so a plain screen editor
        sees no ticker fields at all and the fieldset disappears. ``has_perm``
        is True for superusers, so they need no special case here.
        """
        hidden = set()
        if not request.user.has_perm(TICKER_GATE_PERM):
            hidden.update(TICKER_GATE_FIELDS)
        if not request.user.has_perm(TICKER_TEXT_PERM):
            hidden.update(TICKER_TEXT_FIELDS)
        if self._interspersed_blocked_by_ticker(obj):
            hidden.update(INTERSPERSED_FIELDS)
        return hidden

    def get_exclude(self, request, obj=None):
        excluded = list(super().get_exclude(request, obj) or [])
        for field in self._hidden_fields(request, obj):
            if field not in excluded:
                excluded.append(field)
        return excluded

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        hidden = self._hidden_fields(request, obj)
        if not hidden:
            return fieldsets
        # Substitute a note for the interspersed fields rather than letting them
        # vanish: a user without ticker permissions would otherwise see neither
        # those fields nor the ticker ones, with nothing to explain why.
        note = (INTERSPERSED_UNAVAILABLE_FIELD
                if self._interspersed_blocked_by_ticker(obj) else None)
        cleaned = []
        for name, opts in fieldsets:
            fields = []
            for field in opts.get('fields', []):
                if field not in hidden:
                    fields.append(field)
                elif note and field in INTERSPERSED_FIELDS and note not in fields:
                    fields.append(note)
            if not fields:
                continue
            cleaned.append((name, {**opts, 'fields': fields}))
        return cleaned

    @display(description="Interspersed content")
    def interspersed_unavailable(self, obj):
        return ("Not available while the ticker is turned on — a ticker screen cannot play "
                "screen-level interspersed content. Any playlist set here is kept and applies "
                "again once the ticker is turned off. A playlist's own interspersed content "
                "still plays either way.")

    @display(description="Online", boolean=True)
    def show_online(self, obj):
        return obj.online()

    @display(description="Teams")
    def show_teams(self, obj):
        return ", ".join(obj.teams.values_list('name', flat=True))


class TeamMembershipInline(TabularInline):
    model = TeamMembership
    extra = 0
    autocomplete_fields = ('user',)


@admin.register(Team)
class TeamAdmin(ModelAdmin):
    list_display = ('name', 'member_count', 'object_count')
    search_fields = ('name',)
    inlines = [TeamMembershipInline]

    @display(description="Members")
    def member_count(self, obj):
        return obj.members.count()

    @display(description="Owned objects")
    def object_count(self, obj):
        counts = obj.owned_object_counts()
        return ", ".join(f"{n} {label}" for label, n in counts.items() if n) or "—"

    def has_module_permission(self, request):
        return request.user.is_superuser and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        if not request.user.is_superuser:
            return False
        if obj is None:
            return True
        return not obj.blocking_deletion_reasons()

    def delete_model(self, request, obj):
        reasons = obj.blocking_deletion_reasons()
        if reasons:
            raise ValidationError(
                f"Cannot delete team '{obj.name}': " + "; ".join(reasons),
            )
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self.delete_model(request, obj)


admin.site.site_header = settings.ADMIN_SITE_NAME
