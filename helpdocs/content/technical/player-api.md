# What display devices call

Reference for the endpoints a display device uses. You need this when debugging a
screen that isn't behaving, or when checking what a device is actually being
served — you can request any of these yourself while signed in.

All of them are subject to IP access control, except that a signed-in staff
session bypasses it. See [Commissioning a display](help:device-commissioning).

## Content screens

| Endpoint | Returns |
|---|---|
| `/screen/` | The player page for whichever screen matches the caller's address |
| `/screen/<id>` | The player page for one specific screen |
| `/playlist/<id>` | A playlist played directly, ignoring schedules |
| `/api/screen/` | The same as `/screen/`, as data |
| `/api/screen/<id>` | One screen's current playlist, as data |
| `/api/playlist/<id>` | One playlist, as data |
| `/api/unconfigured` | The "not configured" response for an unrecognised device |

The `/screen/` and `/api/screen/` forms are how a device identifies *itself* —
it doesn't need to know its own ID, only its address, which the request carries
anyway.

`/playlist/<id>` is the one behind **View on site** on a playlist. It's the
quickest way to check a playlist's ordering and timings without involving a
schedule.

## The heartbeat

| Endpoint | Returns |
|---|---|
| `/meta`, `/api/meta` | Current state for the calling device |
| `/api/meta/<id>` | Current state for one specific screen |

This is the most important endpoint to understand. Devices poll it every few
seconds, and it returns the playlist currently in force and when that playlist
was last changed. The device compares that timestamp with what it already has and
reloads only when something has actually changed.

**Polling this is what sets `last seen`.** Online/offline on the dashboard is
derived entirely from it: a screen is online if it has polled within the last
{{ config.SCREEN_OFFLINE_AFTER }}. Nothing else updates that timestamp.

Consequences worth remembering:

- A screen that shows offline is not polling. The content configuration is
  irrelevant to that symptom.
- A screen that is online but showing stale content *is* polling, so look at what
  the endpoint returns rather than at the network.
- Opening a screen's URL in your own browser makes it poll, and therefore marks
  that screen as seen. Don't be surprised when a screen you were investigating
  goes green.

## Screens with a ticker

When a screen has a ticker enabled and a non-empty message, the response points
the device at a wrapper page instead of the playlist directly. The wrapper embeds
the normal player and draws the scrolling bar over or beside it, and polls the
same heartbeat endpoint so the message can be changed without touching the
device.

So a screen with a ticker serves a different page shape from one without. If you
are comparing two screens' responses and they look structurally different, check
whether one has a ticker.

## Room displays

| Endpoint | Returns |
|---|---|
| `/event_schedules/` | Routes the caller to its own room, building or group |
| `/event_schedules/<building>/<room>` | One room's screen |
| `/event_schedules/<building>` | A building grid |
| `/event_schedules/<building>/foyer` | A building foyer list |
| `/event_schedules/<building>/group/<id>` | A room group grid |
| `/event_schedules/<building>/group/<id>/foyer` | A room group foyer list |
| `/event_schedules/<building>/<room>/LED` | `AVAILABLE`, `WARNING` or `BUSY` as plain text |
| `/event_schedules/<building>/<room>/book` | Creates an ad-hoc booking |
| `/event_schedules/diagnostic` | Browser capability report |

`/event_schedules/` with nothing after it is the address you configure on a room
display: it resolves the caller's IP to a room, building or group and redirects.
That's why registering the IP is the whole of the configuration.

Room screens poll a state endpoint roughly every ten seconds and reload when
bookings change, which is why a new booking appears on the screen within seconds
rather than waiting for the next calendar pull.

Add `?compact=1` to a room screen's address to force the compact layout on old
hardware.

## Media

Uploaded files are served through the application rather than straight off disk,
so the same access rules apply to them as to the pages that use them. Requests
for paths outside the media directory are rejected.

## What to check when a screen misbehaves

1. Request `/api/meta/<id>` for the screen. Does it name the playlist you expect?
2. If not, the problem is the schedule, not the device.
3. If it does, request `/api/screen/<id>` and check the content list.
4. If that's right too, the problem is at the device — browser, network, or
   cache.
