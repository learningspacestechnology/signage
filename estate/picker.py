"""The screen form's two-step room picker: a building, then a room in it.

The estate runs to thousands of rooms, and the datastore carries a handful of
genuine duplicates — two records with the same building and room name, e.g.
"1 George Square — 1.1" as both ``1gs1.1`` and ``georgesq011.1``. A single
estate-wide autocomplete labelled "Building — Room" offered those as identical
rows. Choosing the building first shrinks the list to one building's rooms, and
each room carries its datastore id so the remaining duplicates can be told apart.

Three pieces, used together by ``screens.forms.ScreenAdminForm``:

- ``BuildingChoiceField`` — every building, grouped by campus, searched in the
  browser. Local rather than AJAX so it needs no ``estate.view_building``
  permission on top of the ``estate.view_room`` the room picker already needs.
- ``RoomPickerWidget`` — Django's autocomplete select, pointed at
  ``RoomPickerJsonView`` instead of the site-wide endpoint.
- ``RoomPickerJsonView`` — the stock autocomplete view, narrowed to one building
  and relabelled. It keeps the stock permission check, so an operator without
  ``estate.view_room`` is still refused.
"""

from collections import Counter
from itertools import groupby

from django import forms
from django.contrib.admin.views.autocomplete import AutocompleteJsonView
from django.contrib.admin.widgets import AutocompleteSelect
from django.core.exceptions import PermissionDenied
from django.forms.models import ModelChoiceIterator, ModelChoiceIteratorValue
from unfold.widgets import (UnfoldAdminSelect2MultipleWidget,
                            UnfoldAdminSelect2Widget)

from estate.models import Building, Room


def room_picker_label(room):
    """A room as the picker shows it: its name, then its datastore id.

    No building: the picker only ever lists one building's rooms. The id is the
    one field guaranteed to differ between two records of the same name.
    """
    if room.name == room.lsd_id:
        # The sync names a room after its id when the feed sends no name.
        return room.name
    return f"{room.name} ({room.lsd_id})"


#: Appended to a picker label for a row the datastore no longer returns.
MISSING_SUFFIX = " (missing from datastore)"


class _BuildingsByCampus(ModelChoiceIterator):
    """Buildings as ``<optgroup>`` per campus.

    A building name shared across campuses ("Medical School") gets the campus
    appended too, because once chosen the box shows the option text alone and
    the group heading is gone.

    A field with ``flag_missing`` set also marks buildings the datastore has
    stopped returning — the location group form, where a stale grant is worth
    noticing.
    """

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)
        buildings = list(self.queryset)
        shared = {name for name, n in Counter(b.name for b in buildings).items()
                  if n > 1}
        flag_missing = getattr(self.field, 'flag_missing', False)

        def label(b, campus):
            text = f"{b.name} ({campus.name})" if b.name in shared else b.name
            if flag_missing and b.missing_from_source:
                text += MISSING_SUFFIX
            return text

        for campus, group in groupby(buildings, key=lambda b: b.campus):
            yield (campus.name, [
                (ModelChoiceIteratorValue(self.field.prepare_value(b), b),
                 label(b, campus))
                for b in group
            ])


class BuildingSelectWidget(UnfoldAdminSelect2Widget):
    """Unfold's searchable select, plus a fix for its styling of groups."""

    class Media:
        css = {'screen': ('estate/css/building_picker.css',)}


class BuildingChoiceField(forms.ModelChoiceField):
    iterator = _BuildingsByCampus

    def __init__(self, **kwargs):
        kwargs.setdefault('queryset', Building.objects.select_related('campus')
                          .order_by('campus__name', 'name'))
        kwargs.setdefault('widget', BuildingSelectWidget(attrs={
            'data-allow-clear': 'true', 'data-placeholder': ''}))
        super().__init__(**kwargs)


class BuildingSelectMultipleWidget(UnfoldAdminSelect2MultipleWidget):
    """The multiple-choice twin of `BuildingSelectWidget`."""

    class Media:
        css = {'screen': ('estate/css/building_picker.css',)}


class BuildingMultipleChoiceField(forms.ModelMultipleChoiceField):
    """Several buildings, grouped by campus like `BuildingChoiceField`.

    Used for location group grants rather than an autocomplete, because an
    autocomplete shows a bare building name and "Medical School" is two
    different buildings. The grouping and the campus suffix tell them apart.
    """

    iterator = _BuildingsByCampus

    def __init__(self, **kwargs):
        self.flag_missing = kwargs.pop('flag_missing', False)
        kwargs.setdefault('queryset', Building.objects.select_related('campus')
                          .order_by('campus__name', 'name'))
        kwargs.setdefault('widget', BuildingSelectMultipleWidget(attrs={
            'data-placeholder': ''}))
        super().__init__(**kwargs)


class RoomPickerWidget(AutocompleteSelect):
    """An autocomplete for a FK to Room, filtered by a building box beside it.

    The form names that box by setting ``data-building-input`` to its element
    id; ``room_picker.js`` reads it.
    """

    url_name = '%s:estate_room_picker'

    @property
    def media(self):
        # autocomplete.js is repeated on purpose. Media merging only orders
        # files that share a list, so appending room_picker.js on its own lets
        # it load first, and Django's init then runs last and discards the
        # building parameter.
        return super().media + forms.Media(js=[
            'admin/js/jquery.init.js',
            'admin/js/autocomplete.js',
            'estate/js/room_picker.js',
        ])

    def value_omitted_from_data(self, data, files, name):
        """Absent means empty, as for a checkbox.

        The script disables the select while no building is chosen, and a
        disabled select is not submitted. Django's default reads absence as
        "not on the form", and because ``Screen.room`` has a default,
        ``construct_instance`` then keeps the old room, so clearing the building
        would silently leave the screen where it was.
        """
        return False


class RoomPickerJsonView(AutocompleteJsonView):
    """Rooms in one building, for ``RoomPickerWidget``.

    No ``building`` parameter means no results rather than the whole estate:
    the labels carry no building name, so an estate-wide list would be the
    ambiguous one this picker exists to replace.
    """

    def process_request(self, request):
        term, model_admin, source_field, to_field_name = (
            super().process_request(request))
        # The stock checks accept any FK the caller names; get_queryset filters
        # on building_id, which only Room has.
        if model_admin.model is not Room:
            raise PermissionDenied
        return term, model_admin, source_field, to_field_name

    def get_queryset(self):
        building = self.request.GET.get('building', '')
        if not building.isdigit():
            return Room.objects.none()
        return super().get_queryset().filter(building_id=int(building))

    def serialize_result(self, obj, to_field_name):
        return {**super().serialize_result(obj, to_field_name),
                'text': room_picker_label(obj)}
