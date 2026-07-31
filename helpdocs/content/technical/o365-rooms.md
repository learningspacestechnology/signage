# O365 rooms

Room displays are driven by Outlook room mailboxes. This page covers keeping that
inventory correct: bringing new rooms in, putting them in the right building, and
dealing with the ones that stop working.

Everything here is under **O365 rooms** in the sidebar.

## How the pieces fit

There are two separate things, linked only by email address:

- An **O365 room** — a mailbox discovered in your Microsoft tenant. This list is
  rebuilt by the sync and is read-only; you don't create these.
- A **Room** — a room in {{ config.ADMIN_SITE_NAME }}, belonging to a building,
  with display settings. This is what a physical screen shows.

**Assigning** a mailbox to a building creates the Room. Until then the mailbox is
known but unused.

## The sync

The sync runs {{ config.ROOM_SYNC_SCHEDULE }} and:

- adds mailboxes that are new to the tenant;
- refreshes the official name of rooms already assigned;
- flags mailboxes whose calendar it cannot read;
- flags mailboxes that have disappeared from the tenant.

Bookings themselves are pulled separately, {{ config.ROOM_EVENT_SCHEDULE }}.

To run the sync immediately, use **Sync O365 rooms now** at the top right of
either O365 rooms tab. It's queued as a background job, so give it a moment and
reload — the page doesn't wait for it.

## Assigning new rooms

Open the **Unassigned** tab. Mailboxes are grouped by the building name Microsoft
suggests, which is a hint only — trust your own knowledge of the estate over it.

![Unassigned O365 room mailboxes](screenshot:o365-unassigned)

**One at a time:** pick the building from the dropdown on the row and choose
**Assign**.

**In bulk:** tick the mailboxes, pick a building in the form at the top of the
page, and choose the bulk assign action. Much faster when a whole building
arrives at once.

Either way a Room is created. Then open it under **Rooms** to set its display
name and display options — see
[Room and building displays](help:room-displays).

## Managing assigned rooms

The **Assigned per Building** tab lists every room already in use, grouped by
building.

![Assigned O365 rooms](screenshot:o365-assigned)

From each row you can:

- **Toggle booking** — turn ad-hoc booking from the screen on or off, without
  opening the room.
- **Move to another building** — pick a building and choose Move.
- **Open the live screen** for that room, to check what it's showing.
- **Edit the room** for the full settings form.

!!! warning "Moving a room drops it from room groups"
    A room group requires all its members to be in the group's building. Moving a
    room out of that building removes it from any such group automatically and
    without confirmation. Check afterwards whether a group display has lost a
    room it should still have.

## No calendar access

Mailboxes listed here exist in the tenant, but the sync could not read their
calendars. Their displays will show no bookings.

This is a permissions problem in Microsoft, not something you can fix here. The
usual causes are the room mailbox not granting calendar read to the application,
or the mailbox being of a type that doesn't expose a calendar. Take the list to
whoever administers the tenant.

Rooms in this state are excluded from the Unassigned list, so you can't assign a
mailbox that would never work.

## Missing from tenant

Mailboxes that back a real room here, but which the last sync could not find in
Microsoft at all — usually deleted or renamed on the Microsoft side.

The room keeps its last known bookings and then goes stale. Either get the
mailbox restored, or delete the room here if it's genuinely gone. The list links
straight to each room so you can check what would be lost.

Mailboxes that were never assigned are cleaned up silently and don't appear here.

## Ad-hoc booking

For **Book Now** to appear on a room screen, the room needs both:

- a **calendar address**, and
- **allow booking** switched on.

Bookings are created in the real Outlook calendar as *Adhoc Booking*, starting
now, capped at four hours, and automatically shortened so they never overlap the
next booking. The user-facing behaviour is described in
[Booking a room from its screen](help:booking-a-room).

If Confirm fails with a message about not reaching the booking service, the
application couldn't write to the calendar — check the **No calendar access**
list, and confirm the room-calendar app registration is healthy. That is a
*different* registration from the sign-in one, as
[Microsoft sign-in](help:sso-and-entra) explains.

## Configuration

The room-calendar credentials, and the optional delegated mode that authenticates
as a service account with Exchange read access to the mailboxes instead of as the
application itself, are set at deployment time. Neither is editable here.
