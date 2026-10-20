"""Users shown and found by name in the Teams and Location groups admins.

A username is the person's sign-in address (``s1234567@ed.ac.uk``, see
`advertising.forms`), which is what ``str(user)`` gives — so the stock member
rows and member picker show a column of UUNs. Everything here puts the name
first, keeping the address alongside because two people can share a name.

- ``user_label`` / ``user_name`` — the two ways a user is written.
- ``MEMBER_SEARCH_FIELDS``, ``members_by_name``, ``names_only_when_autocompleting``
  — what a group changelist needs to list and search its members.
- ``UserPickerWidget`` / ``UserPickerJsonView`` — Django's autocomplete pointed
  at a view that labels results by name, as `estate.picker`'s room picker does
  for rooms. The site-wide endpoint labels with ``str(obj)`` and has no hook.
- ``UserPickerInlineMixin`` — wires both into a membership inline.

A plain module, not an admin: `screens.admin` and `estate.admin` import it,
and importing `advertising.admin` from them would run its re-registrations.
"""

from django.contrib.admin.views.autocomplete import AutocompleteJsonView
from django.contrib.admin.widgets import AutocompleteSelect
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch

#: Appended to a group admin's own ``search_fields``. Django applies every
#: search term in one ``filter()``, so "Jane Smith" must match one member,
#: not a Jane and a Smith.
MEMBER_SEARCH_FIELDS = ('members__first_name', 'members__last_name',
                        'members__username', 'members__email')

USER_ORDERING = ('last_name', 'first_name', 'username')


def user_name(user):
    """The person's name, or their username if no name is set yet."""
    return user.get_full_name() or user.username


def user_label(user):
    """The name, then the username — e.g. "Jane Smith (s1234567@ed.ac.uk)"."""
    name = user.get_full_name()
    return f"{name} ({user.username})" if name else user.username


def members_by_name():
    """Prefetch a group's members in the order the list shows them."""
    return Prefetch('members', queryset=User.objects.order_by(*USER_ORDERING))


def names_only_when_autocompleting(request, search_fields):
    """``('name',)`` for the site-wide autocomplete, else ``search_fields``.

    A team or location group is also picked by autocomplete on a user's page,
    where matching members would make "Lib" offer every group with a Libby in
    it alongside Library.
    """
    if getattr(request.resolver_match, 'url_name', None) == 'autocomplete':
        return ('name',)
    return search_fields


class UserPickerWidget(AutocompleteSelect):
    """An autocomplete for a FK to User, served by ``UserPickerJsonView``."""

    url_name = '%s:user_picker'


class UserPickerJsonView(AutocompleteJsonView):
    """The stock autocomplete view, relabelled with ``user_label``.

    Searching is unchanged: it runs UserAdmin's search fields, which already
    include first and last name. The stock permission check still applies.
    """

    def process_request(self, request):
        term, model_admin, source_field, to_field_name = (
            super().process_request(request))
        # The stock checks accept any FK the caller names; this view's labels
        # only make sense for users.
        if model_admin.model is not User:
            raise PermissionDenied
        return term, model_admin, source_field, to_field_name

    def serialize_result(self, obj, to_field_name):
        return {**super().serialize_result(obj, to_field_name),
                'text': user_label(obj)}


class UserPickerInlineMixin:
    """A membership inline whose ``user`` rows and picker show names.

    Put before ``TabularInline`` in the bases, and leave ``user`` out of
    ``autocomplete_fields``: passing the widget here is what overrides it.
    """

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name != 'user':
            return super().formfield_for_foreignkey(db_field, request, **kwargs)
        kwargs['widget'] = UserPickerWidget(
            db_field, self.admin_site, using=kwargs.get('using'))
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        # The widget renders an already-saved row's option through this.
        field.label_from_instance = user_label
        return field

    def get_queryset(self, request):
        return (super().get_queryset(request).select_related('user')
                .order_by(*(f'user__{f}' for f in USER_ORDERING)))
