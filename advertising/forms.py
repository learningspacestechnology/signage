"""Admin forms for the `advertising` project.

`PreprovisionUserCreationForm` is the streamlined "add user" form used by the
custom `UserAdmin`. It lets an admin pre-create an account for someone who will
sign in via Microsoft Entra, in a single step: enter their sign-in address as
the email (username is derived from it), optionally a password (blank -> the
account can only be used via SSO), plus name / staff access / teams / location groups.

The email is the link key: `advertising.entra_auth.EntraOIDCBackend` matches an
incoming login to an existing user by email (then username), so a stub created
here is picked up on first sign-in instead of being duplicated.

`GroupPermissionForm` and `UserGridChangeForm` edit permissions through the
grid in `advertising.permission_grid` rather than Django's raw list.
"""

from django import forms
from django.contrib.auth.models import Group, User
from django.db.models import Q

from unfold.forms import UserChangeForm as UnfoldUserChangeForm
from unfold.forms import UserCreationForm as UnfoldUserCreationForm
from unfold.widgets import (
    UnfoldAdminEmailInputWidget,
    UnfoldAdminSelect2MultipleWidget,
)

from advertising.permission_grid import (
    OtherPermissionsField,
    PermissionGridField,
    PermissionGridFormMixin,
)

OTHER_PERMISSIONS_HELP = (
    "Held, but not part of the grid above. Most are Django internals that do "
    "nothing in this interface. Untick one to remove it."
)


class PreprovisionUserCreationForm(UnfoldUserCreationForm):
    """One-step add form for SSO (Entra) users.

    Mirrors the backend's auto-provisioning: username derived from the email,
    unusable password unless one is explicitly supplied.
    """

    email = forms.EmailField(
        required=True,
        widget=UnfoldAdminEmailInputWidget,
        help_text="The user's full UUN based email address (UUN@ed.ac.uk). Their first "
        "SSO login links to this account, so it must match exactly.",
    )
    teams = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),  # replaced in __init__
        required=False,
        widget=UnfoldAdminSelect2MultipleWidget,
        help_text="Teams whose content this user can manage.",
    )
    location_groups = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),  # replaced in __init__
        required=False,
        widget=UnfoldAdminSelect2MultipleWidget,
        help_text="Location groups whose places this user can see. Without one "
        "(or Estate directory → See every location) they see no screens.",
    )

    class Meta(UnfoldUserCreationForm.Meta):
        model = User
        fields = ("email", "first_name", "last_name", "is_staff")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Local import: models aren't ready at module import time.
        from estate.models import LocationGroup
        from screens.models import Team

        self.fields["teams"].queryset = Team.objects.all()
        self.fields["location_groups"].queryset = LocationGroup.objects.all()

        # SSO accounts normally have no password; make it optional.
        self.fields["password1"].required = False
        self.fields["password2"].required = False

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        # Reject anything that would collide on the backend's match key
        # (email, then username) and create a confusing duplicate later.
        if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exists():
            raise forms.ValidationError(
                "A user with this email or username already exists."
            )
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        # Derive the username from the email (matches the backend's own
        # auto-create in entra_auth.EntraOIDCBackend.authenticate).
        user.username = self.cleaned_data["email"][:150]
        if not self.cleaned_data.get("password1"):
            user.set_unusable_password()
        if commit:
            user.save()
        return user


class GroupPermissionForm(PermissionGridFormMixin, forms.ModelForm):
    capabilities = PermissionGridField(
        label="What members can do",
        help_text="Each box grants everything that action needs. Edit and "
        "Delete tick View for you. Teams and location groups decide whose "
        "content and which screens members see; this decides what they can "
        "do with them.",
    )
    other_permissions = OtherPermissionsField(
        label="Other permissions", help_text=OTHER_PERMISSIONS_HELP)
    grid_m2m = "permissions"

    class Meta:
        model = Group
        fields = ("name",)


class UserGridChangeForm(PermissionGridFormMixin, UnfoldUserChangeForm):
    capabilities = PermissionGridField(
        label="Direct permissions",
        help_text="Granted to this person alone, on top of their groups. "
        "Prefer a group: it is far easier to see who can do what.",
    )
    other_permissions = OtherPermissionsField(
        label="Other direct permissions", help_text=OTHER_PERMISSIONS_HELP)
    grid_m2m = "user_permissions"
