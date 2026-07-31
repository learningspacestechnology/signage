# Things that go wrong

Organised by symptom. For content not appearing on a screen, the user-facing
[troubleshooting page](help:users/troubleshooting) covers the configuration
causes first — check those before assuming a technical fault.

## The application won't start

### `O365_CLIENT_ID not set in settings.py`

The room-schedules code requires all three room-calendar credentials to be
present, and raises on import if any is missing or blank. The application will
not start at all — this is not a room-display problem, it's a total outage.

Note that a blank value counts as missing. A configuration key present but empty
fails exactly like an absent one.

Fix: supply all three values, or remove the room-schedules component. Deployment
request either way.

## Displays

### A display shows "screen not configured"

Its address isn't registered, or has changed. The page prints the current
address — read it off and update the record. See
[Commissioning a display](help:device-commissioning).

### `403 Access denied: IP not registered`

The device's address isn't recognised. If the address on the record looks right,
the likely cause is that the application is seeing a *different* address than you
expect — behind a reverse proxy, every request can appear to come from the proxy
unless forwarded-address handling is configured to match the proxy chain.

Two symptoms point at this specifically:

- **every** display fails at once, rather than one;
- displays worked before a networking or proxy change.

That is a deployment-side setting. Report it as "the forwarded-client-address
setting doesn't match our proxy chain" — that's the fix, and it's not something
you can change here.

### A browser gets redirected to sign-in instead of a 403

Same underlying cause. A request that looks like a browser asking for a page is
sent to the sign-in page rather than shown a bare error, on the assumption that a
person has wandered onto a display URL. Devices requesting data get the 403.

### Screens show offline but are clearly working

Online status comes solely from the device polling the heartbeat endpoint. If
displays are showing correct content but reporting offline, they are rendering a
cached page and no longer polling — usually an old browser that has stopped
running the page's scripts. Reload the device.

Check by requesting the heartbeat endpoint for that screen yourself; see
[What display devices call](help:player-api). Note that doing so marks the screen
as seen, so do it after you've noted the timestamp, not before.

### One display is fine, another on the same wall isn't

Compare what each is actually served rather than their configuration. Two screens
can share a schedule and still differ — a ticker on one changes the whole
response shape.

## Rooms

### A room display shows no bookings

In order:

1. Does the room have a **calendar address**? Without one it has no source of
   bookings.
2. Is it in the **No calendar access** list? Then the failure is Microsoft-side
   permissions.
3. Is it in the **Missing from tenant** list? The mailbox no longer exists.
4. Has the booking-pull job run? Check **Task Results**.

See [O365 rooms](help:o365-rooms) and [Background jobs](help:scheduled-tasks).

### Bookings are stale everywhere

One job feeds every room display. Check **Task Results** for the booking pull. If
it's failing, the traceback names the cause; if nothing is recorded at all, the
worker or scheduler isn't running, which is a deployment matter.

### A room dropped out of a group display

Check whether the room was moved to another building. A group requires all its
members to share the group's building, so moving a room out silently removes it
from that group. Move it back, or re-add it to a group in its new building.

### Book Now doesn't appear

All four must hold: the room is free now, the next booking isn't within 15
minutes, the room has a calendar address, and **allow booking** is on.

### Booking fails with a service error

The write to Outlook failed. Nothing was booked. Check the **No calendar access**
list and the health of the room-calendar registration — which is a *different*
registration from the sign-in one.

## Accounts

### Someone can sign in but sees "account not configured"

No staff status. Their account exists already. See
[Microsoft sign-in](help:sso-and-entra).

### Someone signs in but sees "no team assigned"

Staff status but no team. Assign one — see
[Users and teams](help:users-and-teams). They cannot reach any part of the
interface until you do, including the help pages, so they can't self-serve.

### Someone has two accounts

The pre-provisioned email didn't match their real sign-in address. Consolidate
onto the account they're actually using and deactivate the other.

### A user can see the sidebar entry but gets an error opening it

Team and permission layers disagreeing — they have the team but not the model
permission. See [How access works](help:access-model).

## Content

### Expired content is still playing

The cleanup job isn't running. Check **Task Results**.

### Content with a start date never appeared

The playlist-update job isn't running. Same place.

### A website won't display

Many sites refuse to be embedded in another page. Open the address in a normal
browser tab: if it loads there but not on screen, the site is blocking embedding
and no configuration here will change that. Use a different source.

## Gathering useful information

When escalating, include:

- the screen or room name, and the device's address;
- what the device shows versus what `/api/meta/<id>` returns for it;
- the relevant rows from **Task Results**;
- whether it affects one display or all of them — that single fact separates a
  configuration problem from an infrastructure one.
