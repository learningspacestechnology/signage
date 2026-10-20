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
2. Tick what its members can do in the **What members can do** grid.
3. Save, then open each user and add them to the group.

![A group's permission grid](screenshot:group-form)

The **Groups** list shows what each group grants and how many members it has.

### Reading the grid

Each row is one area of the interface, named and grouped as it is in the
sidebar. The columns are **View**, **Add**, **Edit** and **Delete**. A dash means
the action doesn't exist there: the estate directory, for example, can only be
viewed.

Each box grants everything that action needs, which is often more than one
underlying permission. **Playlists → Edit** also lets members add, reorder and
remove a playlist's content and change what it inherits from; **Schedules →
Edit** covers the schedule's rules. You don't need to find those separately.

Some boxes tick others, because they don't work without them:

- **Add**, **Edit** and **Delete** tick **View** on the same row.
- **Screens → Add** and **Screens → Edit** tick **Estate directory → View**: the
  screen form's room picker reads the estate directory.
- **Room Schedules → Buildings → Delete** ticks **Delete** on Rooms and Room
  groups, because a building's rooms and room groups go with it.

A box ticked this way stays ticked while the box needing it is ticked. If saving
added anything you hadn't ticked, a message says what.

Some rows are single permissions with no View, Add, Edit or Delete. You switch
them on in the **Enabled** column on the right. They are the two ticker
permissions under Screens, **See every location** under the estate directory,
**Never removed for inactivity** and **Technical documentation**. See
[How access works](help:access-model) for what each one does.

Two pairs of names are easy to confuse:

- **Schedules**, under Screens & Playlists, decides which playlist a screen shows
  when. **Periodic tasks**, under Task Management, is the timetable for the
  system's own background jobs. Leave that one to whoever runs the system.
- **Room Schedules → Buildings** and **Rooms** are the display set-up for the
  room-booking screens. The **Estate directory** is the University's own record
  of campuses, buildings and rooms.

!!! warning "Users → Edit and Groups → Edit are administrator access"
    Someone who can edit groups can tick anything for their own group, and
    someone who can edit users can put themselves in any group. Give these only
    to people you would trust with every permission on the page. Neither lets
    anyone become a superuser: only a superuser can change **Superuser status**,
    and everyone else sees it read-only.

### Other permissions

A group set up before the grid existed may hold permissions the grid doesn't
show. The usual case is Django's own *content type* permissions, picked by
mistake because "content" is in the name. These are listed under **Other
permissions**, ticked, each with the reason it isn't in the grid. Untick one to
remove it. The section only appears when there is something in it.

Saving an older group can also **add** permissions. If it could change playlists
but not their entries, saving it with **Playlists → Edit** ticked adds the entry
permissions, so members can now do what the box says.

### Checking what someone can do

Open their user page. **What they can do** shows the grid for everything their
groups and direct permissions add up to. Hover over a tick to see which group
gives it.

![What a user can do, from their groups](screenshot:user-effective-access)

A half-filled box means they hold only part of what that action needs, usually
because the group giving it was set up before the grid. Open that group and save
it to complete it. Permissions outside the grid are listed underneath.

A superuser's page says they hold everything instead, because they do. The view
also works for a deactivated account, showing what reactivating it would give
back.

### Direct permissions

The user page also has a **Direct permissions** grid, collapsed, for
permissions given to one person rather than through a group. Prefer a group:
direct grants don't show in the **Groups** list, so they are the ones that get
forgotten.

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

The other way round, the **Teams** list has a **Member names** column. Its
search box finds a team by a member's name or email address as well as by the
team's own name. Search for a full name ("Jane Smith") to find only teams that
person is in, not every team with a Jane and a Smith.

A user's own page shows the same thing for one person. Superusers get a
**Teams** block and a **Location groups** block at the bottom of the page, with
one row per membership, and can add or remove rows there. Anyone else who can
open the page sees a read-only **Teams and locations** section instead.

Wherever you pick a person — the member rows on a team or location group — they
are shown by name, with their email address in brackets, and you can type
either to find them. Someone who has never signed in and was added without a
name shows as their email address alone.

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
delete their membership row, either on the team or in the **Teams** block on the
user's own page. Location groups work the same way: remove the member row on the
group, or in the **Location groups** block on the user's page.

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
3. Add **members** using the membership rows. Type part of a person's name or
   email address to find them.
4. Save.

You can also add someone to a team from their own user page, in the **Teams**
block.

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
