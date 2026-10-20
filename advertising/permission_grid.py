"""The permission grid on the Group and User pages.

What the grid offers lives in `advertising.permission_catalogue`; this module
turns it into a form field, saves it, and renders the read-only version the
User page uses to show everything a person can do.

Saving never drops a permission silently. A box is shown ticked when its
*primary* permission is held, and anything held that no ticked box accounts for
— a Django internal picked by mistake, half of a bundle — is listed under
**Other permissions**, ticked, for the admin to keep or untick. A box whose
bundle was only partly held is completed on save, which only ever adds.

A plain module, not an admin, for the same reason as `advertising.user_picker`.
"""

from collections import defaultdict

from django import forms
from django.contrib.auth.models import Permission
from django.template.loader import render_to_string
# Unfold's own checkbox styling, so the grid matches every other checkbox in
# the admin. Not public API, but a rename fails at import, not silently.
from unfold.widgets import (CHECKBOX_CLASSES,
                            UnfoldAdminCheckboxSelectMultipleWidget)

from advertising import permission_catalogue as catalogue

TEMPLATE = 'admin/auth/permission_grid.html'


def permission_key(permission):
    """'app_label.codename', the form ``has_perm`` and the catalogue use."""
    return f'{permission.content_type.app_label}.{permission.codename}'


def permissions_by_key():
    return {permission_key(p): p
            for p in Permission.objects.select_related('content_type')}


def explain(key):
    """Why a permission is listed under Other permissions."""
    if key in catalogue.HIDDEN:
        return catalogue.HIDDEN[key]
    cells = catalogue.bundles_containing(key)
    if cells:
        return f"Part of {' / '.join(c.label for c in cells)}, which is not ticked."
    return "Not in the grid yet."


def split_held(held):
    """``(boxes to tick, permissions no ticked box accounts for)``.

    The ticked boxes include the ones they imply, so the form shows exactly
    what saving it will grant even before any JavaScript runs.
    """
    boxes = catalogue.implied(catalogue.ticked(held))
    return boxes, set(held) - catalogue.permissions_for(boxes)


# ---- Rendering --------------------------------------------------------------

def _grid(cell_context):
    """Sections, rows and cells for the template.

    ``cell_context(cell)`` returns the per-box dict for the mode being drawn —
    a checkbox, or a read-only state.
    """
    sections = []
    for section in catalogue.SECTIONS:
        rows = []
        for row in section.rows:
            rows.append({
                'label': row.label,
                'description': row.description,
                'warning': row.warning,
                'has_actions': bool(row.actions),
                'cells': [
                    cell_context(catalogue.CELLS[f'{row.key}:{action}'])
                    if action in row.actions else None
                    for action, _label in catalogue.ACTIONS
                ],
                'extras': [cell_context(catalogue.CELLS[extra.key])
                           for extra in row.extras],
            })
        sections.append({'title': section.title, 'rows': rows,
                         'has_actions': any(r['has_actions'] for r in rows),
                         'has_extras': any(r['extras'] for r in rows)})
    return {'sections': sections,
            'action_labels': [label for _action, label in catalogue.ACTIONS],
            'extras_heading': catalogue.EXTRAS_HEADING}


class PermissionGridWidget(forms.Widget):
    template_name = TEMPLATE

    class Media:
        css = {'all': ('screens/css/permission_grid.css',)}
        js = ('screens/js/permission_grid.js',)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        checked = set(value or ())
        prefix = context['widget']['attrs'].get('id') or name

        def checkbox(cell):
            return {
                'key': cell.key,
                'label': cell.label,
                'description': cell.description,
                'id': f'{prefix}_{cell.key.replace(":", "_")}',
                'checked': cell.key in checked,
                # The whole closure, so the script needs no catalogue of its own.
                'implies': ' '.join(sorted(catalogue.implied({cell.key}) - {cell.key})),
            }

        context['grid'] = {**_grid(checkbox), 'name': name, 'readonly': False,
                           'checkbox_classes': ' '.join(CHECKBOX_CLASSES)}
        return context

    def render(self, name, value, attrs=None, renderer=None):
        # Through the main template engine: the form renderer only searches
        # app directories, not the project `templates/` this lives in beside
        # the read-only rendering below.
        return render_to_string(self.template_name,
                                self.get_context(name, value, attrs))

    def value_from_datadict(self, data, files, name):
        getlist = getattr(data, 'getlist', None)
        return getlist(name) if getlist else data.get(name, [])

    def value_omitted_from_data(self, data, files, name):
        # Unticking every box submits nothing, and that is a real answer.
        return False

    def id_for_label(self, id_):
        # Many inputs and no single one to point a <label for> at.
        return None


class PermissionGridField(forms.MultipleChoiceField):
    widget = PermissionGridWidget

    def __init__(self, **kwargs):
        kwargs.setdefault('required', False)
        super().__init__(
            choices=[(key, cell.label) for key, cell in catalogue.CELLS.items()],
            **kwargs)


class OtherPermissionsField(forms.ModelMultipleChoiceField):
    """Held permissions the grid does not account for. Untick to remove.

    The queryset is set per form to exactly what the object already holds, so
    this can only ever keep or drop — a crafted POST cannot add through it.
    """

    widget = UnfoldAdminCheckboxSelectMultipleWidget

    def __init__(self, **kwargs):
        kwargs.setdefault('required', False)
        super().__init__(queryset=Permission.objects.none(), **kwargs)

    def label_from_instance(self, obj):
        return (f"{obj.content_type.app_label} › {obj.content_type.name}: "
                f"{obj.name} — {explain(permission_key(obj))}")


class PermissionGridFormMixin:
    """For a ModelForm whose permission M2M is edited through the grid.

    Declare ``capabilities = PermissionGridField()`` and
    ``other_permissions = OtherPermissionsField()`` on the form — a plain
    mixin's fields would not be collected — and set ``grid_m2m``.
    Leave the M2M itself out of the form's fields.
    """

    grid_m2m = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._by_key = permissions_by_key()
        held = set()
        if self.instance.pk:
            held = {permission_key(p) for p in getattr(self.instance, self.grid_m2m)
                    .select_related('content_type')}
        boxes, self._other_held = split_held(held)
        if 'capabilities' in self.fields:
            self.fields['capabilities'].initial = sorted(boxes)
        if 'other_permissions' in self.fields:
            field = self.fields['other_permissions']
            field.queryset = (Permission.objects
                              .filter(pk__in=[self._by_key[k].pk for k in self._other_held])
                              .select_related('content_type')
                              .order_by('content_type__app_label',
                                        'content_type__model', 'codename'))
            field.initial = list(field.queryset)
        #: Boxes saving added because the chosen ones need them; for a message.
        self.grid_auto_ticked = set()

    def _save_m2m(self):
        super()._save_m2m()
        if 'capabilities' not in self.cleaned_data:
            return
        chosen = set(self.cleaned_data['capabilities'])
        self.grid_auto_ticked = catalogue.implied(chosen) - chosen
        if 'other_permissions' in self.cleaned_data:
            kept = {permission_key(p) for p in self.cleaned_data['other_permissions']}
        else:
            # Not on the form at all — nothing to keep or drop, so keep it all.
            kept = self._other_held
        keys = catalogue.permissions_for(chosen) | kept
        getattr(self.instance, self.grid_m2m).set(
            [self._by_key[k] for k in keys if k in self._by_key])

    def auto_ticked_labels(self):
        return [catalogue.CELLS[k].label for k in sorted(self.grid_auto_ticked)]


# ---- Read-only views --------------------------------------------------------

def permission_sources(user):
    """'app_label.codename' -> where this user gets it: group names or "direct".

    Straight from the tables rather than ``get_all_permissions()``, which is
    empty for an inactive account — and a deactivated account is exactly when
    someone wants to see what reactivating it would give back.
    """
    sources = defaultdict(set)
    for permission in user.user_permissions.select_related('content_type'):
        sources[permission_key(permission)].add('direct')
    for group in user.groups.prefetch_related('permissions__content_type'):
        for permission in group.permissions.all():
            sources[permission_key(permission)].add(group.name)
    return sources


def _from(names):
    if not names:
        return ""
    return "From " + ", ".join(sorted(names, key=lambda n: (n != 'direct', n))) + "."


def render_readonly_grid(sources, *, inactive=False):
    """The grid, read-only. ``sources`` maps 'app_label.codename' to the set of
    places it comes from, which may be empty when there is only one."""

    def state(cell):
        held = [p for p in cell.permissions if p in sources]
        context = {'label': cell.label, 'description': cell.description,
                   'state': '', 'title': ''}
        if not held:
            return context
        missing = [p for p in cell.permissions if p not in sources]
        context['state'] = 'partial' if missing else 'full'
        context['title'] = _from(set().union(*(sources[p] for p in held)))
        if missing:
            context['title'] += (
                " Incomplete, so parts of it may not work; saving whatever "
                f"grants it completes it (missing {', '.join(missing)}).")
        return context

    # Offered permissions already show in the grid, as a partly-held box.
    other = [{'key': key, 'note': explain(key), 'title': _from(sources[key])}
             for key in sorted(sources) if key not in catalogue.OFFERED]
    return render_to_string(TEMPLATE, {'grid': {
        **_grid(state), 'readonly': True, 'other': other,
        'inactive': inactive}})


def render_effective_access(user):
    """Everything ``user`` can do, and which group (or direct grant) gives it."""
    if user.is_superuser:
        return render_to_string(TEMPLATE, {'grid': {
            'superuser': True, 'inactive': not user.is_active}})
    return render_readonly_grid(permission_sources(user),
                                inactive=not user.is_active)


def render_group_grid(group):
    """A group's grid for someone who may view the group but not change it."""
    return render_readonly_grid({
        permission_key(p): set()
        for p in group.permissions.select_related('content_type')})


def other_held(permissions):
    """Whether a group or user holds anything the grid does not account for,
    i.e. whether its form needs the Other permissions field at all."""
    return bool(split_held({permission_key(p) for p in
                            permissions.select_related('content_type')})[1])


def summarise(held):
    """One line per area for the Groups list: "Content: view, add, edit"."""
    boxes = catalogue.ticked(held)
    action_labels = dict(catalogue.ACTIONS)
    parts = []
    for section in catalogue.SECTIONS:
        for row in section.rows:
            actions = [action_labels[a].lower() for a, _ in catalogue.ACTIONS
                       if f'{row.key}:{a}' in boxes]
            if len(actions) > 1 and len(actions) == len(row.actions):
                parts.append(f"{row.label}: all")
            elif actions:
                parts.append(f"{row.label}: {', '.join(actions)}")
            parts.extend(extra.label for extra in row.extras if extra.key in boxes)
    return parts
