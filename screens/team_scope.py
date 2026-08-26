"""Helpers for scoping querysets to a request's team context."""

from django import forms
from django.db.models import Q

from advertising.middleware import ALL_TEAMS


def scope_to_active_team(qs, request, keep_pks=()):
    """Filter qs to objects owned by the active team (or unfiltered for ALL_TEAMS).

    ``keep_pks`` admits specific rows regardless of ownership. Only picker
    widgets pass it, and only for values the object being edited is *already*
    set to — see `scoped_picker_kwargs`.
    """
    active = getattr(request, 'active_team', None)
    if active is None or active is ALL_TEAMS:
        return qs.distinct()
    keep = [pk for pk in keep_pks if pk is not None]
    if keep:
        return qs.filter(Q(teams=active) | Q(pk__in=keep)).distinct()
    return qs.filter(teams=active).distinct()


def scope_to_user_teams(qs, request, keep_pks=()):
    """Filter qs to objects owned by any team the request user belongs to.

    Superusers see everything. Used for cross-team picker widgets such as
    PlaylistRelation.super_list and PlaylistEntry.source, where the rule is
    'pick from any of your teams' rather than 'pick from the active team'.

    ``keep_pks`` behaves as in `scope_to_active_team`.
    """
    if request.user.is_superuser:
        return qs.distinct()
    in_my_teams = Q(teams__in=request.user.teams.all())
    keep = [pk for pk in keep_pks if pk is not None]
    if keep:
        return qs.filter(in_my_teams | Q(pk__in=keep)).distinct()
    return qs.filter(in_my_teams).distinct()


FOREIGN_CHOICE_NOTE = (
    "Currently set to something owned by another team ({owners}). Leaving it "
    "alone keeps it as it is; choosing something else will change what that "
    "team's screens show."
)

FOREIGN_MULTI_NOTE = (
    "Some of these belong to another team ({owners}) and are ticked because "
    "this content is already in them. Unticking one takes this content off "
    "that team's screens."
)


class ForeignTeamLabelMixin:
    """Marks the choices that are only present because they are already set.

    Unmarked, such a choice is indistinguishable from the operator's own
    content, and repointing it — which changes what the owning team's screens
    show — would look like an ordinary edit.
    """

    foreign_note = ""

    def __init__(self, *args, foreign_labels=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_foreign_labels(foreign_labels)

    def set_foreign_labels(self, labels):
        """Set the flagged choices, and note them in the help text.

        Idempotent: the original help text is kept aside so re-applying to a
        field that already carries a note replaces it rather than stacking.
        """
        self.foreign_labels = labels or {}
        if not hasattr(self, '_base_help_text'):
            self._base_help_text = self.help_text
        if self.foreign_labels:
            owners = ", ".join(sorted(set(self.foreign_labels.values())))
            note = self.foreign_note.format(owners=owners)
            self.help_text = f"{self._base_help_text} {note}".strip()
        else:
            self.help_text = self._base_help_text

    def label_from_instance(self, obj):
        label = super().label_from_instance(obj)
        owners = self.foreign_labels.get(obj.pk)
        return f"{label} (another team: {owners})" if owners else label


class TeamLabelledModelChoiceField(ForeignTeamLabelMixin, forms.ModelChoiceField):
    foreign_note = FOREIGN_CHOICE_NOTE


class TeamLabelledModelMultipleChoiceField(ForeignTeamLabelMixin,
                                           forms.ModelMultipleChoiceField):
    foreign_note = FOREIGN_MULTI_NOTE


def _foreign_pks(model, request, current_pks, scope):
    """Of the values already set, those the scope would have excluded."""
    current = {pk for pk in current_pks if pk is not None}
    if not current:
        return set()
    in_scope = set(
        scope(model.objects.all(), request)
        .filter(pk__in=current).values_list('pk', flat=True)
    )
    return current - in_scope


def _owner_labels(model, foreign):
    return {
        obj.pk: ", ".join(obj.teams.values_list('name', flat=True))
        for obj in model.objects.filter(pk__in=foreign).prefetch_related('teams')
    }


def scoped_picker_kwargs(model, request, current_pks, scope=scope_to_active_team):
    """Build `formfield` kwargs for a team-scoped relation picker.

    Scoping the choices alone is not enough on an object two teams share: a
    value pointing at the *other* team's content falls outside the scope, so the
    field renders with nothing selected — the operator sees no sign anything is
    set — and the form then refuses to save ("This field is required"), or
    quietly drops the value where it is nullable or a multi-select. Either way
    the only route forward repoints the object at the operator's own content and
    changes what the co-owning team's screens play, with nothing on screen to
    say so.

    So keep whatever is already set in the choices, and hand back a field class
    that labels those choices and warns in its help text. Everything else stays
    scoped exactly as before, and a picker with nothing foreign in it gets a
    plain ``ModelChoiceField``.
    """
    foreign = _foreign_pks(model, request, current_pks, scope)
    kwargs = {'queryset': scope(model.objects.all(), request, keep_pks=foreign)}
    if foreign:
        kwargs['form_class'] = TeamLabelledModelChoiceField
        kwargs['foreign_labels'] = _owner_labels(model, foreign)
    return kwargs


def apply_scoped_choices(field, model, request, current_pks,
                         scope=scope_to_active_team):
    """Re-scope a field *declared* on a form, keeping and labelling foreign values.

    Fields built from a model field go through `scoped_picker_kwargs` at
    construction time. A declared one (Source's ``playlists``) already exists by
    then, so it is patched instead — which is why it has to be declared with one
    of the labelled field classes above. Mutate a per-request copy, not the
    shared declared field: ``base_fields`` inherits the very same field object
    into every form class the factory produces.
    """
    foreign = _foreign_pks(model, request, current_pks, scope)
    field.queryset = scope(model.objects.all(), request, keep_pks=foreign)
    field.set_foreign_labels(_owner_labels(model, foreign) if foreign else None)
    return field
