# How access works

There are **three independent authorisation layers**, and they do different jobs:

- **Teams** control *whose* content, playlists, schedules and screens you see.
- **Location groups** control *where*: which campuses, buildings and rooms,
  and so which screens.
- **Groups and permissions** control *what you can do*.

They compose. A user sees the intersection: screens in their team **and** in
their locations, filtered by the permissions they hold. Getting one right and
another wrong is the single most common cause of "I can't see it" and "they can
do too much".

## Account flags

| Flag | Effect |
|---|---|
| **Active** | Off means the account cannot sign in at all. This is how you offboard someone. |
| **Staff status** | Required to reach the interface at all. Everyone who uses {{ config.ADMIN_SITE_NAME }} has it. |
| **Superuser status** | Bypasses every permission check, sees every team and every location, and can manage teams and location groups. Grant sparingly. |

An account that signs in successfully but lacks **staff status** is shown an
"account not configured" page and is *not* signed in. See
[Microsoft sign-in](help:sso-and-entra).

## Layer 1: Teams

Content, playlists, screens and schedules each belong to one or more teams. A
user sees an object only if they share a team with it.

- A user's **active team** is remembered per session, and shown at the top of
  every page. Users belonging to several teams switch between them; they never
  see two teams at once.
- **Superusers** default to an **All teams** view spanning everything, and can
  switch to a single team to see what a member of that team would see. This is
  the fastest way to reproduce a user's report.
- When a regular user creates something, it is automatically filed under their
  active team. They cannot choose, and the team field is hidden from them.
- **Only superusers can change which teams an object belongs to.** This is
  enforced when the form is saved, not merely hidden, so it can't be worked
  around.

A staff user with **no team at all** is blocked from the interface entirely and
shown a "no team assigned" page — including the help documentation. Assigning a
team is therefore part of onboarding, not an afterthought.

## Layer 2: Location groups

A location group is a named set of campuses, buildings and rooms with a list of
members. A user limited to location groups sees only screens in those places,
and only those places in the estate directory and the room picker. Content,
playlists and schedules are not tied to a place and are unaffected.

- **Superusers** and holders of **Can see all locations** are not limited.
  That permission comes through the **All locations** group, which every staff
  account that existed when location groups were introduced was added to.
- Everyone else sees the places their groups grant — and **nothing** if they
  are in no group. Unlike a missing team, that doesn't block the interface: they
  can sign in and work with content, but see no screens.
- **Only superusers can manage location groups** and their members.

[Location access](help:location-access) covers setting them up.

## Layer 3: Groups and permissions

Permissions are standard Django model permissions — add, change, delete and view,
per model. Assign them through **Groups** rather than to individuals; a group per
role is far easier to audit than fifty individual permission sets.

Reasonable starting roles:

| Group | Permissions |
|---|---|
| **Content editor** | Add/change/view content and playlists |
| **Scheduler** | The above, plus add/change/view schedules and screens |
| **Technical** | The above, plus room schedules, and technical documentation access |

### Four permissions worth knowing about

The ticker tape is split across two of them, so the shape of the display and the
message on it can be delegated separately.

**`screens.change_ticker_settings`** — lets a user turn the ticker on and choose
its layout, deciding whether the bar overlays the content or the content shrinks
to make room.

**`screens.change_ticker_text`** — lets a user write and style the scrolling
message, without any say over whether the ticker is on.

Neither is granted by `screens.change_screen`. A user holding neither sees no
ticker fields on the screen form and no ticker documentation, so the feature is
invisible until someone grants it deliberately.

**`estate.access_all_locations`** ("Can see all locations") — exempts a user
from location groups entirely. Hand it out through the **All locations** group
rather than directly, so the **Users** list can show who has it at a glance.

**`helpdocs.view_technical_docs`** — grants access to this documentation set.
Superusers have it implicitly. Grant it via a group to anyone doing the work
described here.

## How they compose

For every list in the interface:

1. The queryset is filtered to the active team.
2. Screens and estate records are also filtered to the user's locations.
3. Then the standard permission checks apply.

So a user with full content permissions but no team membership sees nothing; a
user in the right team with no location group sees content but no screens; and
a user with both but no permissions sees the sidebar entry but cannot open it.
When someone reports a problem, establish which of the three layers is missing
before changing anything.

## Two access controls that aren't about users

Worth knowing because they cause reports that look like permission problems:

- **IP access control** gates the display-facing URLs — screen and room pages
  outside the admin interface. A device whose address isn't registered is
  refused. See [Commissioning a display](help:device-commissioning).
- **Signed-in staff bypass it entirely**, which is why an administrator can open
  a screen URL in their browser and see it working while the display in the
  corridor gets a 403.
