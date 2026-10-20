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
| **Active** | Off means the account cannot sign in at all. This is how you offboard someone.{% if config.ACCOUNT_INACTIVITY_DAYS %} Also switched off automatically after {{ config.ACCOUNT_INACTIVITY_DAYS }} days unused — see [Users and teams](help:users-and-teams).{% endif %} |
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

Groups decide what members can do: view, add, edit or delete, area by area.
Each group is edited through a grid whose rows match the sidebar. See
[Users and teams](help:users-and-teams) for how to read it. Assign permissions
through groups rather than to individuals: a group per role is far easier to
audit than fifty individual permission sets.

Reasonable starting roles, in the grid's terms:

| Group | Tick |
|---|---|
| **Content editor** | Content and Playlists: View, Add, Edit |
| **Scheduler** | The above, plus Schedules and Screens: View, Edit |
| **Screen editor** | Screens: View, Edit, and nothing else. Members can rename a screen, place it in a room, and point it at a schedule, but can't change the schedule itself |
| **Technical** | The above, plus the Room Schedules rows and Technical documentation |

**Screens → Edit** also ticks **Estate directory → View**, because the room
picker needs it. A screen editor still sees only the screens in their team and
their locations.

### Single permissions worth knowing about

These are switched on in the grid's **Enabled** column. None of View, Add, Edit
or Delete includes them.

**Ticker: turn it on and choose its layout** and **Ticker: write and style the
message**, under Screens. The ticker is split so that the shape of the display
and the message on it can be delegated separately. The first decides whether the
bar overlays the content or the content shrinks to make room. The second covers
the scrolling message and how it looks, with no say over whether the ticker is
on. **Screens → Edit** grants neither, and a user with neither sees no ticker
fields on the screen form and no ticker documentation.

**See every location**, under Estate directory. Exempts a user from location
groups entirely. Hand it out through the **All locations** group rather than
directly, so the **Users** list shows who has it at a glance.

**Never removed for inactivity**, under Users, Groups & Teams. Exempts an account
from automatic removal. Hand it out through the **Exempt from inactivity
removal** group.

**Technical documentation**, under Help. Grants access to this documentation
set. Superusers have it implicitly. Grant it through a group to anyone doing the
work described here.

### Permissions that amount to administrator access

**Users → Edit** and **Groups → Edit**. Someone who can edit groups can tick
anything for their own group, and someone who can edit users can put themselves
in any group. Treat both as administrator access.

They stop short of superuser: only a superuser can change **Superuser status**,
and anyone else sees it read-only.

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
