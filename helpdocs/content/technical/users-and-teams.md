# Users and teams

The procedures for getting someone access, changing it, and taking it away. Read
[How access works](help:access-model) first if you haven't — the two
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
6. **Leave the password blank.** A blank password means the account can only be
   used through Microsoft sign-in, which is what you want. Only set one for a
   service or test account that must sign in with a password.
7. Save.

![Pre-provisioning a user](screenshot:user-add)

The username is derived from the email address automatically — you don't set it.

!!! warning "Team membership is not optional"
    A staff user with no team is locked out of the entire interface, including
    this documentation. Assign at least one team as part of creating the account,
    not later.

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
2. Choose its permissions.
3. Open the user and add them to the group.

See [How access works](help:access-model) for suggested roles and for the two
non-obvious permissions — the ticker text permission and technical documentation
access.

## Changing someone's password

Only relevant for password accounts. Open the user, and use the password change
link on the form. Microsoft accounts have no password here to change.

## Removing access

**Untick Active.** That's it — the account can no longer sign in by any route,
while their history and the record of what they created stay intact.

Do not delete the user. Deleting loses the audit trail, and the "created by"
attribution on their content.

If they're changing role rather than leaving, remove them from the team instead:
open the team and delete their membership row.

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
