from django import forms
from django.contrib import admin, messages
from django.core.cache import cache
from django.db.models import (BooleanField, Count, Exists, ExpressionWrapper,
                              IntegerField, Min, OuterRef, Prefetch, Q, Subquery)
from django.db.models.functions import Coalesce
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from unfold.admin import ModelAdmin, TabularInline
from unfold.widgets import UnfoldAdminCheckboxSelectMultipleWidget

from estate.location_scope import (ALL_LOCATIONS, rooms_granted_by,
                                   scope_screens, scope_to_locations,
                                   sees_all_locations, visible_room_ids)
from estate.models import (Building, BuildingLink, Campus, LocationGroup,
                           LocationGroupMembership, Room, RoomLink)
from estate.models.access import stale_grants_q
from estate.picker import MISSING_SUFFIX, BuildingMultipleChoiceField
from estate.tasks import sync_estate
from screens.models import Screen

#: Shared by the two dispatch routes below. LocMemCache is the configured
#: backend, so this stops a double-click, not a second uwsgi worker — which is
#: all it needs to do for an idempotent read-only sync.
SYNC_LOCK_KEY = 'estate_sync_dispatch_lock'
SYNC_LOCK_SECONDS = 60


def dispatch_sync(request, redirect_to):
    """Queue a sync run, or say why it was not queued. Shared by both routes."""
    if not cache.add(SYNC_LOCK_KEY, True, SYNC_LOCK_SECONDS):
        messages.info(
            request,
            "An estate sync was requested moments ago and is still running.")
        return redirect(redirect_to)
    sync_estate.delay()
    messages.info(
        request,
        "Estate sync dispatched. Campuses, buildings and rooms will refresh "
        "once the worker finishes — usually within a few minutes.")
    return redirect(redirect_to)


class ReadOnlyMirrorAdmin(ModelAdmin):
    """A viewer over rows the nightly sync owns.

    Read-only is enforced at ``has_*_permission`` rather than through
    ``readonly_fields``, which would still render a Save button and still
    write. An edit made here survives only until the next sync run, so that
    would be a control that silently discards the operator's work; returning
    False makes Django render the honest view-only form instead.

    False for superusers too, deliberately. The fix for a wrong room name is
    upstream in the datastore, not a local edit that quietly reverts.

    Rows are scoped to the requester's location groups (`estate.location_scope`)
    before any subclass annotates them. That also scopes every list filter that
    reads this queryset, and every autocomplete searching through it — the
    screen form's room picker included.
    """

    def get_queryset(self, request):
        return scope_to_locations(super().get_queryset(request), request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # A word rather than @display(boolean=True). The boolean icon renders a red
    # cross for False, so a wholly healthy list came out as a column of red
    # crosses meaning "fine" — confidently misleading, and conveying the state
    # by colour alone into the bargain.
    @admin.display(description="From datastore", ordering="missing_from_source")
    def show_missing(self, obj):
        return "Missing" if obj.missing_from_source else "—"


def _visible_rooms_q(request, path):
    """A ``Count(filter=...)`` limiting ``path`` to rooms the requester may see.

    None for an unrestricted requester, so the unscoped query stays exactly as
    it was. The object rows are already scoped; this scopes what is counted
    *inside* them — a room grant reveals its building, not its other rooms.
    """
    ids = visible_room_ids(request)
    if ids is ALL_LOCATIONS:
        return None
    return Q(**{f'{path}__in': ids})


def _visible_screen_counts(request, path):
    """Screens the requester can see, counted per ``path``, as a Subquery.

    A Subquery rather than a second ``Count()`` on the same queryset: chained
    aggregates multiply each other's rows. ``distinct=True`` because team
    scoping joins the teams M2M — the same reasoning already written out in
    advertising/admin.py's dashboard counts.
    """
    counts = (
        scope_screens(Screen.objects.all(), request)
        .filter(**{path: OuterRef('pk')})
        .order_by()
        .values(path)
        .annotate(n=Count('pk', distinct=True))
        .values('n')
    )
    return Coalesce(Subquery(counts, output_field=IntegerField()), 0)


@admin.register(Campus)
class CampusAdmin(ReadOnlyMirrorAdmin):
    list_display = ('name', 'code', 'building_count', 'room_count', 'show_missing')
    search_fields = ('name', 'code')
    list_filter = ('missing_from_source',)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            n_buildings=Count(
                'buildings', distinct=True,
                filter=_visible_rooms_q(request, 'buildings__rooms')),
            n_rooms=Count(
                'buildings__rooms', distinct=True,
                filter=_visible_rooms_q(request, 'buildings__rooms')),
        )

    @admin.display(description="Buildings", ordering="n_buildings")
    def building_count(self, obj):
        return obj.n_buildings

    @admin.display(description="Rooms", ordering="n_rooms")
    def room_count(self, obj):
        return obj.n_rooms


class EstatesCodeFilter(admin.SimpleListFilter):
    """Buildings holding at least one room with the chosen Estates code.

    Through the rooms, because that is where the code lives: picking 0228
    lists both buildings Estates files under it, which is the point.

    Plain links rather than Unfold's searchable DropdownFilter, which only
    submits with ``list_filter_submit``. That turns the panel into a form, and
    Unfold's link-filter template then re-sends the campus filter as
    ``lookup_val.0`` — the first *character* on Django 4.2, where the value
    is a string rather than Django 5's list, so campus 12 becomes campus 1.
    """
    title = "Estates building code"
    parameter_name = 'estates_code'

    def lookups(self, request, model_admin):
        codes = (scope_to_locations(Room.objects.all(), request)
                 .exclude(building_code='')
                 .order_by('building_code')
                 .values_list('building_code', flat=True).distinct())
        return [(code, code) for code in codes]

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        # A subquery rather than a join, so a building with many rooms under
        # the code comes back once without needing DISTINCT.
        return queryset.filter(pk__in=Room.objects.filter(
            building_code=self.value()).values('building'))


@admin.register(Building)
class BuildingAdmin(ReadOnlyMirrorAdmin):
    list_display = ('name', 'campus', 'list_estates_codes', 'room_count',
                    'screen_count', 'screens_link', 'show_missing')
    list_filter = (('campus', admin.RelatedOnlyFieldListFilter), EstatesCodeFilter,
                   'missing_from_source')
    # Searching an Estates code finds every building holding a room with it —
    # "everything Estates calls 0228" is two of our buildings, which is the
    # point. The reverse join can repeat a building; the admin adds DISTINCT.
    search_fields = ('name', 'campus__name', 'campus__code', 'rooms__building_code')
    list_select_related = ('campus',)
    readonly_fields = ('show_estates_codes',)
    fields = ('name', 'campus', 'show_estates_codes', 'missing_from_source')

    def get_queryset(self, request):
        visible = _visible_rooms_q(request, 'rooms')
        coded = ~Q(rooms__building_code='')
        return super().get_queryset(request).annotate(
            n_rooms=Count('rooms', distinct=True, filter=visible),
            n_screens=_visible_screen_counts(request, 'room__building'),
            # Sorts the codes column by each building's lowest code.
            first_code=Min('rooms__building_code',
                           filter=coded & visible if visible else coded),
        ).prefetch_related(
            # Building.estates_codes is a query per building, so the column
            # reads these instead: one query for the whole page. No string
            # aggregate is portable between SQLite (dev) and MySQL (prod).
            Prefetch('rooms', to_attr='coded_rooms', queryset=(
                scope_to_locations(Room.objects.all(), request)
                .exclude(building_code='')
                .only('building', 'building_code').order_by('building_code'))),
        )

    @admin.display(description="Estates building codes", ordering="first_code")
    def list_estates_codes(self, obj):
        codes = dict.fromkeys(room.building_code for room in obj.coded_rooms)
        return ", ".join(codes) or "—"

    @admin.display(description="Rooms", ordering="n_rooms")
    def room_count(self, obj):
        return obj.n_rooms

    # Labelled "(your teams)" because the number *is* scoped — to the active
    # team and to the requester's locations: an Alpha user sees 3 where a
    # superuser across all teams sees 7. Without the label it reads as an
    # estate fact.
    @admin.display(description="Screens (your teams)", ordering="n_screens")
    def screen_count(self, obj):
        return obj.n_screens

    @admin.display(description="Estates building codes")
    def show_estates_codes(self, obj):
        return ", ".join(obj.estates_codes) or "—"

    @admin.display(description="")
    def screens_link(self, obj):
        if not obj.n_screens:
            return "—"
        return format_html(
            '<a class="inline-block font-semibold h-6 leading-6 px-2 rounded-default '
            'text-[11px] uppercase whitespace-nowrap bg-primary-100 text-primary-700 '
            'dark:bg-primary-500/20 dark:text-primary-400" href="{}">Screens</a>',
            reverse('admin:estate_building_screens', args=[obj.pk]),
        )


@admin.register(Room)
class RoomAdmin(ReadOnlyMirrorAdmin):
    list_display = ('name', 'building', 'campus_name', 'room_status',
                    'capacity', 'building_code', 'show_active', 'screen_count',
                    'show_missing')
    list_filter = (
        ('building__campus', admin.RelatedOnlyFieldListFilter),
        ('building', admin.RelatedOnlyFieldListFilter),
        'active', 'room_status', 'support_type', 'public_campus',
        'missing_from_source',
    )
    # Load-bearing beyond search: the screen form's room picker
    # (estate.picker.RoomPickerJsonView) searches through this admin, and
    # Django's AutocompleteJsonView 404s without it.
    # building_code so an Estates code finds its rooms across the building
    # names it spans.
    search_fields = ('name', 'lsd_id', 'building__name', 'building_code')
    fields = ('lsd_id', 'name', 'building', 'active', 'room_status', 'capacity',
              'building_code', 'public_campus', 'optime_index', 'support_type',
              'service_provider', 'voip_number', 'latitude', 'longitude',
              'address', 'missing_from_source')
    list_select_related = ('building', 'building__campus')
    change_list_template = 'admin/estate/room/change_list.html'

    def get_queryset(self, request):
        # select_related for Room.__str__, which the location group form's
        # autocomplete calls once per result.
        return super().get_queryset(request).select_related('building').annotate(
            n_screens=_visible_screen_counts(request, 'room'),
        )

    @admin.display(description="Campus", ordering="building__campus__name")
    def campus_name(self, obj):
        return obj.building.campus.name

    # Words, for the same reason as show_missing. Not a dash for the common
    # case either, as show_missing uses: under a heading that asks a question,
    # a dash reads as "no".
    @admin.display(description="Open today", ordering="active")
    def show_active(self, obj):
        return "Yes" if obj.active else "Inactive"

    @admin.display(description="Screens (your teams)", ordering="n_screens")
    def screen_count(self, obj):
        return obj.n_screens


class AllLocationsOnlyMixin:
    """Hide an admin from location-restricted users.

    For the display-link admins, which list links across the whole estate and
    so would reveal buildings and rooms outside a user's location groups.
    """

    def has_module_permission(self, request):
        return (sees_all_locations(request)
                and super().has_module_permission(request))

    def has_view_permission(self, request, obj=None):
        return (sees_all_locations(request)
                and super().has_view_permission(request, obj))

    def has_change_permission(self, request, obj=None):
        return (sees_all_locations(request)
                and super().has_change_permission(request, obj))

    def has_delete_permission(self, request, obj=None):
        return (sees_all_locations(request)
                and super().has_delete_permission(request, obj))


@admin.register(BuildingLink)
class BuildingLinkAdmin(AllLocationsOnlyMixin, ModelAdmin):
    list_display = ('display_building', 'estate_building', 'linked_by', 'linked_at')
    list_select_related = ('display_building', 'estate_building', 'linked_by')
    search_fields = ('display_building__name', 'estate_building__name')

    def has_add_permission(self, request):
        # Links are made on the dedicated page, where the suggestions are.
        return False


@admin.register(RoomLink)
class RoomLinkAdmin(AllLocationsOnlyMixin, ModelAdmin):
    list_display = ('display_room', 'estate_room', 'linked_by', 'linked_at')
    list_select_related = ('display_room', 'estate_room', 'linked_by')
    search_fields = ('display_room__name', 'estate_room__name')

    def has_add_permission(self, request):
        return False


def _grant_count(through, column):
    """How many rows of a grant table belong to each group, as a Subquery.

    One Subquery per table rather than a ``Count()`` per M2M: four M2M joins on
    one queryset would multiply campuses by buildings by rooms by members.
    """
    counts = (through.objects.filter(**{column: OuterRef('pk')})
              .order_by().values(column).annotate(n=Count('pk')).values('n'))
    return Coalesce(Subquery(counts, output_field=IntegerField()), 0)


class NeedsReviewFilter(admin.SimpleListFilter):
    title = "needs review"
    parameter_name = 'needs_review'

    def lookups(self, request, model_admin):
        return [('1', "Grants missing from the datastore")]

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(stale_grants_q())
        return queryset


def _flag_missing(field):
    """Make a model choice field append `MISSING_SUFFIX` to stale rows' labels."""
    plain = field.label_from_instance
    field.label_from_instance = lambda obj: (
        plain(obj) + MISSING_SUFFIX if obj.missing_from_source else plain(obj))


class LocationGroupForm(forms.ModelForm):
    # Declared rather than left to the admin: the admin's default for a M2M is
    # a flat list of bare building names, and "Medical School" is two
    # different buildings. This groups them by campus.
    buildings = BuildingMultipleChoiceField(
        required=False, flag_missing=True,
        help_text=LocationGroup._meta.get_field('buildings').help_text)
    campuses = forms.ModelMultipleChoiceField(
        queryset=Campus.objects.all(), required=False,
        widget=UnfoldAdminCheckboxSelectMultipleWidget,
        help_text=LocationGroup._meta.get_field('campuses').help_text)
    add_rooms_from = BuildingMultipleChoiceField(
        required=False, label="Add every room currently in",
        help_text="A one-off shortcut, applied when you save: adds each room "
                  "these buildings hold today to Rooms, so you can then "
                  "remove the ones you don't want. Unlike granting the "
                  "building, rooms added to it later are not included.")

    class Meta:
        model = LocationGroup
        fields = ('name', 'description', 'campuses', 'buildings', 'rooms')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        rooms = self.fields.get('rooms')
        if rooms is not None:
            # Room.__str__ reads the building; the autocomplete renders the
            # already-chosen rooms through this queryset.
            rooms.queryset = rooms.queryset.select_related('building')
            _flag_missing(rooms)
        _flag_missing(self.fields['campuses'])


class LocationGroupMembershipInline(TabularInline):
    model = LocationGroupMembership
    extra = 0
    autocomplete_fields = ('user',)
    verbose_name = "member"
    verbose_name_plural = "members"


@admin.register(LocationGroup)
class LocationGroupAdmin(ModelAdmin):
    """Named sets of places, granted to users. See `estate.models.access`.

    Superuser-only, like `TeamAdmin`: a location group grants access, so
    letting anyone else edit one would let them widen their own.
    """

    form = LocationGroupForm
    list_display = ('name', 'show_grants', 'rooms_covered', 'member_count',
                    'show_needs_review')
    list_filter = (NeedsReviewFilter,)
    search_fields = ('name',)
    autocomplete_fields = ('rooms',)
    readonly_fields = ('stale_grants',)
    inlines = [LocationGroupMembershipInline]
    fieldsets = (
        (None, {'fields': ('name', 'description')}),
        ("Places", {
            'description': (
                "Members see these places and everything inside them, plus "
                "the building and campus of any room granted on its own. A "
                "member of several groups sees all of their places."),
            'fields': ('stale_grants', 'campuses', 'buildings', 'rooms',
                       'add_rooms_from'),
        }),
    )

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        # The stale-grants warning only when there is something to review; a
        # permanent "Missing from the datastore: —" would train people to skip it.
        if obj is not None and LocationGroup.objects.filter(
                stale_grants_q(), pk=obj.pk).exists():
            return fieldsets
        return [(name, {**opts, 'fields': tuple(
                    f for f in opts['fields'] if f != 'stale_grants')})
                for name, opts in fieldsets]

    def get_queryset(self, request):
        through = LocationGroup
        return super().get_queryset(request).annotate(
            n_campuses=_grant_count(through.campuses.through, 'locationgroup'),
            n_buildings=_grant_count(through.buildings.through, 'locationgroup'),
            n_rooms=_grant_count(through.rooms.through, 'locationgroup'),
            n_members=_grant_count(LocationGroupMembership, 'group'),
            needs_review=ExpressionWrapper(
                stale_grants_q(), output_field=BooleanField()),
        )

    def save_related(self, request, form, formsets, change):
        # super() first: its save_m2m() does rooms.set() from the form, which
        # would undo anything added before it.
        super().save_related(request, form, formsets, change)
        buildings = form.cleaned_data.get('add_rooms_from')
        if not buildings:
            return
        group = form.instance
        before = group.rooms.count()
        group.rooms.add(*Room.objects.filter(building__in=buildings))
        added = group.rooms.count() - before
        messages.success(request, "Added {n} room{s} from {names}.".format(
            n=added, s='' if added == 1 else 's',
            names=", ".join(b.name for b in buildings)))

    @admin.display(description="Grants")
    def show_grants(self, obj):
        parts = [
            (obj.n_campuses, 'campus', 'campuses'),
            (obj.n_buildings, 'building', 'buildings'),
            (obj.n_rooms, 'room', 'rooms'),
        ]
        return ", ".join(f"{n} {one if n == 1 else many}"
                         for n, one, many in parts if n) or "Nothing"

    # A query per row. Acceptable on a superuser-only list of a few dozen
    # groups, and it is the one number that answers "what does this give?".
    @admin.display(description="Rooms covered")
    def rooms_covered(self, obj):
        return rooms_granted_by([obj.pk]).count()

    @admin.display(description="Members", ordering='n_members')
    def member_count(self, obj):
        return obj.n_members

    @admin.display(description="Needs review", ordering='needs_review')
    def show_needs_review(self, obj):
        return "Missing places" if obj.needs_review else "—"

    @admin.display(description="Missing from the datastore")
    def stale_grants(self, obj):
        if obj is None or obj.pk is None:
            return "—"
        stale = [
            *(("Campus", c.name) for c in
              obj.campuses.filter(missing_from_source=True)),
            *(("Building", f"{b.name} ({b.campus.name})") for b in
              obj.buildings.filter(missing_from_source=True)
              .select_related('campus')),
            *(("Room", str(r)) for r in
              obj.rooms.filter(missing_from_source=True)
              .select_related('building')),
        ]
        if not stale:
            return "—"
        return format_html(
            "<p>The datastore no longer returns these, so they may now cover "
            "nothing. A building renamed upstream arrives as a new building: "
            "grant that one instead and remove the old.</p><ul>{}</ul>",
            format_html_join("", "<li>{}: {}</li>", stale))

    def has_module_permission(self, request):
        return request.user.is_superuser and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
