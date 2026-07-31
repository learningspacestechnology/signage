# How access works

There are **two independent authorisation layers**, and they do different jobs:

- **Teams** control *what you can see*.
- **Groups and permissions** control *what you can do*.

They compose. A user sees the intersection: objects in their team, filtered by
the permissions they hold. Getting one right and the other wrong is the single
most common cause of "I can't see it" and "they can do too much".

## Account flags

| Flag | Effect |
|---|---|
| **Active** | Off means the account cannot sign in at all. This is how you offboard someone. |
| **Staff status** | Required to reach the interface at all. Everyone who uses {{ config.ADMIN_SITE_NAME }} has it. |
| **Superuser status** | Bypasses every permission check, sees every team, and can manage teams and team membership. Grant sparingly. |

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

## Layer 2: Groups and permissions

Permissions are standard Django model permissions — add, change, delete and view,
per model. Assign them through **Groups** rather than to individuals; a group per
role is far easier to audit than fifty individual permission sets.

Reasonable starting roles:

| Group | Permissions |
|---|---|
| **Content editor** | Add/change/view content and playlists |
| **Scheduler** | The above, plus add/change/view schedules and screens |
| **Technical** | The above, plus room schedules, and technical documentation access |

### Two permissions worth knowing about

**`screens.change_ticker_text`** — lets a user write and style the scrolling
message on a screen without being a superuser. Turning the ticker on and choosing
its layout stays superuser-only, so the shape of the display is controlled while
the message itself can be delegated. A user with neither sees no ticker fields at
all.

**`helpdocs.view_technical_docs`** — grants access to this documentation set.
Superusers have it implicitly. Grant it via a group to anyone doing the work
described here.

## How they compose

For every list in the interface:

1. The queryset is filtered to the active team.
2. Then the standard permission checks apply.

So a user with full content permissions but no team membership sees nothing, and
a user in the right team with no permissions sees the sidebar entry but cannot
open it. When someone reports a problem, establish which of the two layers is
missing before changing anything.

## Two access controls that aren't about users

Worth knowing because they cause reports that look like permission problems:

- **IP access control** gates the display-facing URLs — screen and room pages
  outside the admin interface. A device whose address isn't registered is
  refused. See [Commissioning a display](help:device-commissioning).
- **Signed-in staff bypass it entirely**, which is why an administrator can open
  a screen URL in their browser and see it working while the display in the
  corridor gets a 403.
