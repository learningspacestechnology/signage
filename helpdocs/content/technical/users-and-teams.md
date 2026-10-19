# Users and teams

The procedures for getting someone access, changing it, and taking it away. Read
[How access works](help:access-model) first if you haven't — the three
authorisation layers behave differently and this page assumes you know which is
which.

## Adding a user before their first sign-in

Pre-provisioning is the normal path. It creates the account so it's ready and
correctly scoped the first time the person signs in with Microsoft.

1. Go to **Users** and choose **Add user**.
2. Enter their **email address**. This is the link key — the first Microsoft
   sign-in is matched to this account by email, so **it must match their sign-in
   address exactly**. Get this wrong and they end up with a second, empty
   account.
3. Fill in **first name** and **last name**. These are filled in from Microsoft
   on first sign-in if you leave them blank, so they're optional.
4. Tick **Staff status**. Without it they can sign in but are shown an "account
   not configured" page.
5. Choose their **Teams**. This field is only shown to superusers, and it is
   enforced on save, not merely hidden.
6. Choose their **Location groups** — the places whose screens they will see.
   Also superuser-only. To let them see every location instead, leave this
   empty and add them to the **All locations** group once the account exists.
   See [Location access](help:location-access).
7. **Leave the password blank.** A blank password means the account can only be
   used through Microsoft sign-in, which is what you want. Only set one for a
   service or test account that must sign in with a password.{% if not config.PASSWORD_LOGIN_AVAILABLE %}
   Password sign-in is switched off on this deployment, so a password set here
   won't work until it's switched back on — see
   [Password sign-in](help:sso-and-entra).{% endif %}
8. Save.

![Pre-provisioning a user](screenshot:user-add)

The username is derived from the email address automatically — you don't set it.

!!! warning "Team membership and location access are not optional"
    A staff user with no team is locked out of the entire interface, including
    this documentation. A staff user with no location group, and not in **All
    locations**, can sign in but sees no screens. Assign both as part of
    creating the account, not later.

### If the account already exists

The form refuses an email that collides with an existing user's **email or
username**. That's deliberate: a duplicate would silently split someone's
access. If you hit it, find the existing account and edit that instead.

You'll also hit this after someone has already tried to sign in — the attempt
creates a stub account for them. That's the account to edit; you don't need to
create anything.

## Granting permissions

Assign permissions through **Groups**, not to individuals.

1. Go to **Groups** and create one per role, if you haven't already.
2. Choose its permissions. The **Permissions** box is a search field, not a
   list to scroll: click it and type part of what you're after — a model name
   like `playlist`, or an action like `Can change` — and pick from the matches.
   Each choice becomes a tag you can remove with its ×.
3. Open the user and add them to the group.

See [How access works](help:access-model) for suggested roles and for the
non-obvious permissions — the two ticker permissions and technical documentation
access.

## Checking who is in which team

The **Users** list has a **Teams** column showing every team an account belongs
to, and a **Locations** column showing where they can see screens. To narrow the
list to one team, open **Filters** and use **By team**; **By location access**
does the same for locations.

![The users list](screenshot:users-list)

The filter's **No team** option is the one to reach for: it finds the accounts
that can see nothing at all. A user lands there between being created and being
given a team, and again if their last membership is removed — they can still
sign in, they just arrive at an empty interface.

## Changing someone's password

Only relevant for password accounts. Open the user, and use the password change
link on the form. Microsoft accounts have no password here to change.{% if not config.PASSWORD_LOGIN_AVAILABLE %}
While password sign-in is switched off on this deployment, a changed password
won't work until it's switched back on.{% endif %}

## Removing access

**Untick Active.** That's it — the account can no longer sign in by any route,
while their history and the record of what they created stay intact.

Do not delete the user. Deleting loses the audit trail, and the "created by"
attribution on their content.{% if config.ACCOUNT_INACTIVITY_DAYS %} A deactivated account is still deleted
automatically once nobody has used it for {{ config.ACCOUNT_INACTIVITY_DAYS }} days —
see **Inactive accounts** below. To keep its history for good, add it to the
**Exempt from inactivity removal** group.{% endif %}

If they're changing role rather than leaving, remove them from the team instead:
open the team and delete their membership row. Location groups work the same
way: remove the member row on the group, or on the user's own page.

## Inactive accounts

{% if config.ACCOUNT_INACTIVITY_DAYS %}An account nobody has used for **{{ config.ACCOUNT_INACTIVITY_DAYS }} days** is
deactivated automatically, then deleted **{{ config.ACCOUNT_DELETION_GRACE_DAYS }} days** after that.
The check runs {{ config.ACCOUNT_CHECK_SCHEDULE }}.

**What counts as use.** Signing in by either route, or having a session still
open — someone who stays signed in and works every day is not caught out by
rarely seeing the sign-in page. An account nobody has ever signed in to counts
from when it was created, so a pre-provisioned account the person never takes up
goes the same way, as do the empty accounts a refused Microsoft sign-in leaves
behind.

**Superusers are included** — an unused superuser account is exactly the kind
worth removing. The one exception: the check never deactivates the last active
superuser, so someone can always manage users.

**Seeing what's coming.** The **Inactivity** column on **Users** shows what will
happen to each account next, and when. Filter by **inactivity** to list accounts
due in the next 30 days, or deactivated and awaiting deletion. Anyone who can
edit users also gets a notice on the dashboard while something is due within 30
days. Nobody is emailed — the dashboard notice is the only warning.

### Keeping an account

Add it to the **Exempt from inactivity removal** group. Use this for accounts
that are meant to sit unused: the password account kept for when Microsoft
sign-in breaks (see [Password sign-in](help:sso-and-entra)), and service
accounts. The Inactivity column shows them as **Exempt**.

### Undoing a deactivation

Until the account is deleted, open it and tick **Active**. That restarts the
clock, giving the person another {{ config.ACCOUNT_INACTIVITY_DAYS }} days. Adding a deactivated
account to the exempt group stops it being deleted, but it stays deactivated
until you tick **Active**.

### After deletion

Deletion is permanent. The account goes, along with its team and location
memberships and its entries in the change history. Content the person created
stays, without a "created by". If they sign in with Microsoft afterwards, a new
account is created with no access — set it up as you would for anyone new.
{% else %}Automatic removal of unused accounts is switched off on this deployment.
{% endif %}
## Managing teams

Teams are superuser-only, and hidden from everyone else.

### Creating a team

1. Go to **Teams** and choose **Add team**.
2. Give it a **Name**. It's shown in the team switcher at the top of the page, so
   name it after the group of people or the area they look after.
3. Add **members** using the membership rows.
4. Save.

### Deleting a team

A team can only be deleted when it has **no members and owns nothing** — no
content, playlists, screens or schedules. Otherwise the deletion is refused and
the reason lists exactly what's still attached, for example:

```
Cannot delete team 'Old Department': 2 user(s) still assigned;
5 sources still owned; 1 screens still owned
```

To retire a team, work through that list: move its content to another team, or
delete it, then remove the members, then delete the team.

This is enforced at two levels, so it can't be bypassed with a bulk action.

## Moving objects between teams

Only superusers can change an object's teams. Open the object and edit its
**Teams** field.

An object can belong to several teams at once, which is how genuinely shared
content is handled — a notice owned by both *Central* and *Library* is visible
and editable in both.

### What sharing one object implies

A shared object can point at content only one of its teams owns: a schedule owned
by *Central* and *Library* whose default playlist is a *Library* playlist, a
shared playlist inheriting from a *Library* parent, or a shared screen with a
*Library* interspersed playlist.

Members of the other team still see and can save these. The value stays in the
picker even though it is outside their scope, labelled `(another team: Library)`,
with a note under the field. The rest of that team's content stays hidden, so the
only cross-team choice on offer is the one already in use.

The consequence to be aware of when you share something: whoever can edit it can
also *repoint* it, and the other team's screens change with no notification and
no trace beyond the admin log. Share an object between teams when both are
expected to administer it — not merely to let one of them read it.
