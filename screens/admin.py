import copy

from admin_ordering.admin import OrderableAdmin
from django import forms
from django.conf import settings
from django.urls import re_path
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.template.loader import get_template
from django.template.response import TemplateResponse
from django.utils.timesince import timesince
from unfold.admin import ModelAdmin, TabularInline, StackedInline
from unfold.decorators import display

from advertising.middleware import ALL_TEAMS
from estate.location_scope import (scope_screens, scope_to_locations,
                                   sees_all_locations)
from estate.models import Building, Room
from estate.picker import RoomPickerWidget
from screens.forms import (
    PlaylistAssigningSourceForm,
    ScreenAdminForm,
    SourceBulkCreateForm,
)
from screens.models import (
    Playlist,
    PlaylistEntry,
    Schedule,
    ScheduleRule,
    Screen,
    ScreenStatus,
    Source,
    StatusReason,
    Team,
    TeamMembership,
)
from screens.team_scope import (
    apply_scoped_choices,
    scope_to_active_team,
    scope_to_user_teams,
    scoped_picker_kwargs,
)


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

    def get_form(self, request, obj=None, **kwargs):
        """Stash the object under edit for formfield_for_foreignkey.

        Django hands that hook no ``obj``, but a scoped picker has to know what
        it is already set to in order to keep that value selectable — see
        ``scoped_picker_kwargs``.
        """
        request._team_scoped_obj = obj
        return super().get_form(request, obj, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name in ('interspersed_playlist', 'default_playlist', 'schedule'):
            obj = getattr(request, '_team_scoped_obj', None)
            current = [getattr(obj, db_field.attname, None)] if obj else []
            kwargs.update(
                scoped_picker_kwargs(db_field.related_model, request, current))
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


class ScopedPickerInline:
    """Keep the values an inline's existing rows point at selectable.

    The change form's own pickers hit this through ``TeamScopedAdminMixin``;
    a formset reaches it one level down. A row pointing at another team's
    content would drop out of the scoped choices, render blank, and take the
    whole parent form down with it on save — see ``scoped_picker_kwargs``.

    ``get_formset`` is the hook that still has the parent object, so the current
    values are collected there and read back when the fields are built.
    """

    picker_field = None            # the team-scoped FK on the inline model
    parent_fk = None               # the FK back to the object being edited
    picker_scope = staticmethod(scope_to_active_team)

    def get_formset(self, request, obj=None, **kwargs):
        # Keyed by inline class: one change form runs several inlines, and each
        # must read back its own values rather than the previous inline's.
        stash = getattr(request, '_scoped_picker_pks', None)
        if stash is None:
            stash = request._scoped_picker_pks = {}
        attname = self.model._meta.get_field(self.picker_field).attname
        stash[self.__class__] = list(
            self.model._default_manager
            .filter(**{self.parent_fk: obj}).values_list(attname, flat=True)
        ) if obj is not None else []
        return super().get_formset(request, obj, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == self.picker_field:
            current = getattr(request, '_scoped_picker_pks', {}).get(self.__class__, ())
            kwargs.update(scoped_picker_kwargs(
                db_field.related_model, request, current, scope=self.picker_scope,
            ))
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class PlaylistEntryInline(ScopedPickerInline, OrderableAdmin, TabularInline):
    model = PlaylistEntry
    ordering_field = 'number'
    verbose_name_plural = "Content (plays in number order, lowest first)"
    extra = 0
    fields = ('number', 'thumbnail', 'source', 'duration')
    readonly_fields = ('thumbnail',)
    picker_field = 'source'
    parent_fk = 'playlist'
    picker_scope = staticmethod(scope_to_user_teams)


class PlaylistParentsInlineForm(forms.ModelForm):
    def clean(self):
        cleaned = super().clean()
        request = getattr(self, '_request', None)
        super_list = cleaned.get('super_list')
        if request is None or super_list is None or request.user.is_superuser:
            return cleaned
        # A relation the other team wired may already point outside this user's
        # teams. Re-saving that row unchanged has to pass, or the whole playlist
        # form becomes unsaveable; only new or repointed relations are checked.
        if self.instance.pk and self.instance.super_list_id == super_list.pk:
            return cleaned
        if not super_list.teams.filter(pk__in=request.user.teams.values_list('pk', flat=True)).exists():
            raise ValidationError(
                "You can only inherit from a playlist owned by one of your own teams.",
            )
        return cleaned


class PlaylistParentsInline(ScopedPickerInline, TabularInline):
    model = Playlist.parents.through
    form = PlaylistParentsInlineForm
    fk_name = "inheriting_list"
    verbose_name_plural = "Playlists to inherit from"
    verbose_name = "Parent List"
    extra = 0
    picker_field = 'super_list'
    parent_fk = 'inheriting_list'
    picker_scope = staticmethod(scope_to_user_teams)

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


class ScheduleRuleInline(ScopedPickerInline, StackedInline):
    model = ScheduleRule
    extra = 0
    picker_field = 'playlist'
    parent_fk = 'schedule'
    fieldsets = (
        (None, {
            'description': (
                "Each rule points a time window at a playlist. When two rules overlap, the one with the "
                "LOWEST priority number wins. If no rule matches right now, the schedule's default playlist is shown."
            ),
            'fields': ('playlist', 'starts', 'occurrences', 'start_time', 'end_time', 'priority'),
        }),
    )

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
            # Copy first: the declared field is one object shared by every form
            # class the factory builds, so scoping it in place would leak one
            # request's queryset into the next.
            field = copy.deepcopy(form_class.base_fields['playlists'])
            form_class.base_fields['playlists'] = apply_scoped_choices(
                field, Playlist, request,
                obj.playlists.values_list('pk', flat=True) if obj else (),
                scope=scope_to_user_teams,
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


class ScreenStatusFilter(admin.SimpleListFilter):
    """Filter the screens list by the same badge the Status column shows.

    A snapshot, not a saved state: the cutoffs move with the clock, so the
    answer is whatever was true when the page was rendered. That is what the
    operator wants here — "what needs looking at right now" — but it does mean
    two loads a minute apart can legitimately differ.

    Filters on the annotation from `ScreenQuerySet.with_status()` rather than
    rebuilding the conditions, so the badge and the filter cannot disagree.
    """

    title = "status"
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return ScreenStatus.choices

    def queryset(self, request, queryset):
        value = self.value()
        if value in ScreenStatus.values:
            return queryset.filter(derived_status=value)
        return queryset


class EstateRelatedFilter(admin.RelatedOnlyFieldListFilter):
    """A campus/building filter offering only values the reader's screens use.

    Subclassed rather than used bare for two reasons.

    The queryset: `RelatedOnlyFieldListFilter` builds its options from
    `model_admin.get_queryset(request)`, which here carries `with_status()`'s
    three correlated subqueries — pure cost when all that is wanted is a column
    of building ids. Scoping to the active team and the reader's locations
    directly gives the same option set for less.

    The title: unqualified, "building" reads exactly like the room_schedules
    filter next to it, which is a different kind of building entirely.

    Using the *stock* related filter here would be the real bug — its
    `field_choices` applies no queryset restriction at all, so it would list
    every building in the university, almost all matching zero screens. That is
    the trap already documented for `schedule` below, an order of magnitude
    worse.
    """

    filter_title = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.filter_title:
            self.title = self.filter_title

    def has_output(self):
        """Also render whenever a value is actually selected.

        The stock filter hides itself with one option or none, which is right
        on a site with a single building — the feature stays invisible until it
        has something to choose between. But `ChangeList.get_filters` pops a
        filter's lookup parameter whether or not the filter survives
        `has_output()`, so a hidden filter does not merely fail to render, it
        silently *ignores* `?room__building__id__exact=N` and shows every
        screen. The per-building page and the dashboard both link with exactly
        that parameter, so a selected value has to keep the filter alive.
        """
        return super().has_output() or self.lookup_val is not None

    def screens(self, request):
        """The screens whose values this filter offers."""
        return scope_screens(Screen.objects.all(), request)

    def field_choices(self, field, request, model_admin):
        used = self.screens(request).values_list(f'{self.field_path}__pk', flat=True)
        return field.get_choices(
            include_blank=False,
            limit_choices_to={'pk__in': used},
            ordering=self.field_admin_ordering(field, request, model_admin),
        )


#: The two estate filters' lookup parameters. Each reads the other's: the
#: building filter narrows to the selected campus, and the campus filter drops a
#: selected building that a newly chosen campus would not contain.
CAMPUS_LOOKUP = 'room__building__campus__id__exact'
BUILDING_LOOKUP = 'room__building__id__exact'


class EstateCampusFilter(EstateRelatedFilter):
    filter_title = "campus"

    def choices(self, changelist):
        """As the stock filter, but switching campus drops a building not on it.

        Otherwise choosing Central, then Appleton Tower, then King's Buildings
        would keep Appleton Tower selected: the list would empty, and the
        building filter — now narrowed to King's Buildings — would no longer
        even show what is holding it empty. A building that *is* on the chosen
        campus is kept, and "All" keeps any building.
        """
        building = changelist.params.get(BUILDING_LOOKUP)
        choices = super().choices(changelist)
        if building is None:
            yield from choices
            return
        try:
            building_campus = (Building.objects.filter(pk=building)
                               .values_list('campus_id', flat=True).first())
        except (ValueError, ValidationError):
            building_campus = None
        yield next(choices)  # "All"
        for (pk, _), choice in zip(self.lookup_choices, choices):
            if pk != building_campus:
                choice['query_string'] = changelist.get_query_string(
                    {self.lookup_kwarg: pk},
                    [self.lookup_kwarg_isnull, BUILDING_LOOKUP])
            yield choice


class EstateBuildingFilter(EstateRelatedFilter):
    """Buildings holding the reader's screens — on the selected campus, if any.

    Reads the campus from the request rather than from ``params``, because the
    campus filter has already popped its own parameter by the time this one is
    built.
    """

    filter_title = "building"

    def __init__(self, field, request, *args, **kwargs):
        # Before super(), which builds the options through screens().
        try:
            self.campus = int(request.GET[CAMPUS_LOOKUP])
        except (KeyError, ValueError):
            # A junk value is reported by the campus filter itself; offering
            # every building meanwhile is the harmless answer.
            self.campus = None
        super().__init__(field, request, *args, **kwargs)

    def screens(self, request):
        screens = super().screens(request)
        if self.campus is not None:
            screens = screens.filter(room__building__campus_id=self.campus)
        return screens

    def has_output(self):
        """With a campus selected, show even a single building.

        The stock rule — hide with one option — would make the filter vanish
        the moment a campus with one screened building was chosen, which reads
        as the filter breaking rather than as "everything here is in one
        building".
        """
        return super().has_output() or (
            self.campus is not None and bool(self.lookup_choices))


class SupportTypeFilter(admin.SimpleListFilter):
    """Who looks after the screen's room, by the estate directory's support type.

    Only values on screens the reader can see are offered, for the reason the
    estate filters above are scoped: the datastore's own list covers every room
    in the university. A room with no support type is common — over a third of
    the estate — so it gets its own option rather than vanishing.
    """

    title = "support type"
    parameter_name = "support"
    #: Not a value the datastore could send for a support type, which is a
    #: department or service name.
    NOT_RECORDED = "_none"

    def lookups(self, request, model_admin):
        used = set(
            scope_screens(Screen.objects.all(), request)
            .filter(room__isnull=False)
            .order_by().values_list('room__support_type', flat=True).distinct())
        choices = [(value, value) for value in sorted(used - {''}, key=str.casefold)]
        if choices and '' in used:
            choices.append((self.NOT_RECORDED, "Not recorded"))
        return choices

    def has_output(self):
        # Selected means applied, even with nothing on offer — the trap
        # EstateRelatedFilter.has_output describes.
        return super().has_output() or self.value() is not None

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset
        if value == self.NOT_RECORDED:
            return queryset.filter(room__isnull=False, room__support_type='')
        return queryset.filter(room__support_type=value)


class RoomAssignedFilter(admin.SimpleListFilter):
    """"Which screens still have no location" — the commissioning backlog.

    A SimpleListFilter rather than EmptyFieldListFilter for the wording (the
    stock one renders "By room: Empty / Not empty", which reads as a data
    problem rather than a task) and for a stable URL parameter the dashboard
    can link to.

    "In an inactive room" is the other location task: the datastore says the
    room is not open today, so the screen is either somewhere closed or
    assigned to the wrong room. The same condition badges the Room column.
    """

    title = "room"
    parameter_name = "room_set"

    def lookups(self, request, model_admin):
        # A location-restricted reader never sees a screen with no room — no
        # grant can cover one — so "No room set" would always be empty.
        if not sees_all_locations(request):
            return (("yes", "In a room"), ("inactive", "In an inactive room"))
        return (("yes", "In a room"), ("no", "No room set"),
                ("inactive", "In an inactive room"))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(room__isnull=False)
        if self.value() == "no":
            return queryset.filter(room__isnull=True)
        if self.value() == "inactive":
            return queryset.filter(room__active=False)
        return queryset


#: How many past status changes the screen page shows. A screen that flaps can
#: accumulate rows all the way to the retention limit, and nobody reads past
#: the recent ones.
STATUS_HISTORY_SHOWN = 15


@admin.register(Screen)
class ScreenAdmin(TeamScopedAdminMixin, ModelAdmin):
    readonly_fields = ('screen_preview', INTERSPERSED_UNAVAILABLE_FIELD,
                       'show_status', 'show_status_detail', 'status_history',
                       'last_seen', 'last_ping_ok', 'last_ping_attempt')
    list_display = ('name', 'ip', 'show_status', 'show_status_detail', 'last_seen',
                    'show_building', 'show_room', 'schedule', 'show_teams')
    search_fields = ('name', 'ip', 'room__name', 'room__building__name')
    # RelatedOnly, not a bare 'schedule': the stock related filter lists every
    # schedule on the system regardless of team, so a user saw — and could
    # filter by — other teams' schedules, every one of which matched nothing.
    # Limiting to the values present in this admin's own (team-scoped) queryset
    # scopes it correctly and drops the dead options at the same time.
    list_filter = (
        ('schedule', admin.RelatedOnlyFieldListFilter),
        ScreenStatusFilter,
        # Campus before building: the building filter narrows to the campus.
        ('room__building__campus', EstateCampusFilter),
        ('room__building', EstateBuildingFilter),
        SupportTypeFilter,
        RoomAssignedFilter,
    )
    # 'room__building' rather than 'room': the Building column would otherwise
    # cost a second query per row. Campus is not selected because there is no
    # campus column — it is served by the filter alone.
    list_select_related = ('schedule', 'room__building')
    # Room is picked in two steps, building then room — see estate.picker. The
    # room half is an autocomplete, and its view checks `estate.view_room` on
    # the *related* admin, so an operator without it gets a silently empty
    # picker.
    form = ScreenAdminForm
    fieldsets = (
        (None, {
            'fields': ('name', 'schedule', 'ip', 'building', 'room', 'teams',
                       'screen_preview'),
        }),
        ('Status', {
            'fields': ('show_status', 'show_status_detail',
                       'last_seen', 'last_ping_ok', 'last_ping_attempt',
                       'status_history'),
            'description': "Worked out live from the two signals below, not stored. "
                           "Last seen is when the player last checked in; the ping "
                           "times are only filled in when reachability probing is "
                           "turned on.",
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

    def get_queryset(self, request):
        # Location-scoped on top of the mixin's team scoping. with_status() so
        # the badge, the detail column and the sort all read one annotation
        # rather than each screen recomputing its own.
        return scope_to_locations(
            super().get_queryset(request), request).with_status()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'room':
            kwargs['widget'] = RoomPickerWidget(
                db_field, self.admin_site, using=kwargs.get('using'))
            # Load-bearing, not cosmetic. The picker's options come from
            # RoomAdmin, which is already scoped, but the field *validates*
            # against this queryset — and Django's default is every room, so a
            # crafted POST could place a screen outside the user's locations.
            kwargs['queryset'] = scope_to_locations(Room.objects.all(), request)
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == 'room' and field and not sees_all_locations(request):
            # A restricted user only sees screens in their rooms, so one saved
            # with no room would vanish from their list the moment it saved.
            field.required = True
            field.help_text = (
                "Where this screen physically is, from the estate directory. "
                "Required, because you only see screens in your locations.")
        return field

    def get_form(self, request, obj=None, **kwargs):
        form_class = super().get_form(request, obj, **kwargs)
        if 'building' in form_class.base_fields and not sees_all_locations(request):
            # Copy first, as SourceDisplay.get_form does: the declared field is
            # shared by every form class the factory builds.
            field = copy.deepcopy(form_class.base_fields['building'])
            field.queryset = scope_to_locations(field.queryset, request)
            form_class.base_fields['building'] = field
        return form_class

    @display(description="Status history")
    def status_history(self, obj):
        """Recent status changes, rendered rather than run as an inline.

        A read-only TabularInline would be the obvious shape, but the inline
        formset filters the queryset it is handed by the parent FK, and Django
        cannot filter a queryset that has already been sliced — so there is no
        way to cap the rows an inline shows. Rendering it directly keeps the
        limit and costs one query.
        """
        if obj is None or obj.pk is None:
            return "No history yet."
        events = list(obj.status_events.all()[:STATUS_HISTORY_SHOWN])
        if not events:
            return "No status changes recorded yet."
        return get_template("screens/screen_status_history.html").render(
            {"events": events})

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
        if obj is not None and not self.has_change_permission(request, obj):
            # View-only renders every field read-only from the model, and
            # `building` exists only on the form, so Django cannot look it up.
            # The read-only Room already reads "Building — Room".
            hidden.add('building')
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

    @display(description="Status", ordering="status_rank", label={
        "Online": "success",
        "Needs attention": "warning",
        "Offline": "danger",
    })
    def show_status(self, obj):
        return ScreenStatus(self._status(obj)).label

    @staticmethod
    def _status(obj):
        """This screen's status, from the annotation where there is one.

        Both display methods go through here so the badge and the detail beside
        it can never come from two different evaluations of the tiers. The
        annotation is what get_queryset puts there, and judges the whole page
        against a single clock; the fallback covers a Screen that reached a
        display method without going through with_status().
        """
        annotated = getattr(obj, 'derived_status', None)
        return annotated if annotated is not None else obj.status()

    @display(description="Detail")
    def show_status_detail(self, obj):
        """The reason behind the badge, plus how long it has been that way.

        Amber is only actionable if it says *why* — "responds to ping" sends
        someone to the player software, "stopped reporting recently" says wait
        and look again.

        The "since" figure comes from the recorded history, which lags the live
        status by up to one check_screens cycle, so it is only shown while the
        two agree. Otherwise it falls back to the heartbeat, which is always
        current.
        """
        annotated_reason = getattr(obj, 'derived_reason', None)
        if annotated_reason is None:
            reason = obj.status_reason_label()
        else:
            reason = StatusReason(annotated_reason).label if annotated_reason else ""

        since = getattr(obj, 'status_since', None)
        if since and getattr(obj, 'recorded_status', None) == self._status(obj):
            when = f"since {timesince(since)} ago"
        elif obj.last_seen:
            when = f"last seen {timesince(obj.last_seen)} ago"
        else:
            when = ""
        return " · ".join(part for part in (reason, when) if part) or "—"

    @display(description="Building", ordering="room__building__name")
    def show_building(self, obj):
        # room_id rather than room, so an unassigned screen costs no query even
        # if list_select_related is ever dropped.
        return obj.room.building.name if obj.room_id else "—"

    @display(description="Room", ordering="room__name")
    def show_room(self, obj):
        if not obj.room_id:
            return "—"
        if obj.room.active:
            return obj.room.name
        # The room itself is escaped by the template engine; the badge is the
        # same include the per-building screens page uses.
        return get_template("admin/estate/_screen_room_cell.html").render(
            {"room": obj.room})

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
