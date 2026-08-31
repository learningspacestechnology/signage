# Commissioning a display

Getting a new physical screen showing something. The process is the same shape
for both kinds of display, but they're registered in different places.

| Display shows | Register it as | Where |
|---|---|---|
| Playlists and advertising content | A **Screen**, with its IP | **Screens** |
| Room bookings | An **IP address** against a room, building or room group | **Buildings** / **Rooms** / **Room Groups** |

## Step 1: find the device's address

Point the device's browser at the service. Because its address isn't registered
yet, it gets the **"screen not configured"** page — which prints the device's own
IP address and hostname on screen, along with a clock so you can see the page is
live.

Read the address off the display. There's no need to look it up on the network,
and no need for shell access to the device.

The message on that page is
"{{ config.UNCONFIGURED_SCREEN_MESSAGE }}"

!!! tip "Fix the address before anything else"
    Most "the display stopped working" reports are a device that got a different
    address. If a display is showing this page, its address changed — nothing
    else is wrong.

## Step 2a: register a content screen

1. Go to **Screens** → **Add screen**.
2. Set the **Name**, the **Schedule** it should follow, and the **IP** you read
   off the device.
3. Save.

Full detail in [Managing screens](help:users/screens).

## Step 2b: register a room display

Room displays route themselves. Point the device at the room-schedules entry
point and it works out what to show from its address alone — so all you register
is the address, against the thing it should display.

Add the IP address on the **IP addresses** section of:

- a **Room**, for a screen outside a single room;
- a **Building**, for a foyer display covering the building;
- a **Room group**, for a foyer display covering a subset.

!!! warning "Exactly one target"
    An IP address must point at a room, a building **or** a group — never more
    than one, never none. This is enforced by the database as well as the form,
    so a partially-filled row is rejected outright.

Whether the display then shows a grid or a foyer list comes from the target's
**Default display** setting, not from the IP record — see
[Room and building displays](help:room-displays).

## How access control affects displays

Everything outside the admin interface is gated by IP.
{% if config.IP_ACCESS_CONTROL_ENABLED %}It is currently **enabled**.{% else %}It
is currently **disabled**, so any device can load any display URL.{% endif %}

A request is allowed through if **any** of these hold:

- it comes from a signed-in staff user;
- its address matches a registered screen or a registered room/building/group IP;
- it is one of the discovery endpoints, which stay open so a new device can
  announce itself and show you its address.

Otherwise: a browser asking for a page is redirected to the sign-in page, and
anything else gets `403 Access denied: IP not registered`.

This is why **you** can open a screen URL and see it working while the display in
the corridor cannot — you're signed in and it isn't. Always verify from the
device, or from its address, not from your own browser.

## Older display hardware

Some fixed-purpose displays run old browsers. Two things help:

- **Compact mode.** Add `?compact=1` to a room screen's address to force the
  compact layout. It is applied automatically for the oldest known browsers, but
  the override is there when detection doesn't catch one.
- **The diagnostic page.** The room-schedules area has a diagnostic page that
  reports what the device's browser actually supports. Load it on a device that
  renders badly before assuming the display is broken — it usually identifies a
  missing CSS feature immediately.

## Status lights

Some room displays drive a coloured light through a small agent running on the
device itself, which the screen contacts locally. Green means free, amber means
the next booking starts within 15 minutes, red means in use.

If the light is dead but the screen is correct, the agent on the device isn't
running — the display side is fine.

A plain-text status endpoint is also available per room for hardware that can
poll a URL directly, returning `AVAILABLE`, `WARNING` or `BUSY`.

## Commissioning checklist

1. Device shows the "not configured" page — it can reach the service.
2. Address read off the screen and registered.
3. Display reloads and shows content or bookings.
4. For content screens: the screen shows **online** within a minute. See
   [Reading the dashboard](help:users/dashboard).
5. For room displays: bookings match what's in Outlook.
6. If a status light is fitted, it matches the screen.

!!! note "A screen with no schedule still reports online"
    Registering a display marks it as reporting as soon as it polls, whether or
    not it has been given a schedule yet. So step 4 confirms the device is
    talking to the service — it does not confirm anything is scheduled to play.
    A registered screen sitting at "not configured" is expected, and shows
    online while it waits.

    Conversely, a screen you have just registered that shows **needs attention**
    with "responds to ping but is not reporting" has a device on the network at
    that address whose browser isn't loading the page — a kiosk that hasn't been
    pointed at the right URL, most often. See
    [Screen reachability checks](help:screen-reachability).
