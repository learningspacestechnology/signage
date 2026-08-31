# Reading the dashboard

The dashboard is the page you land on after signing in. Everything on it is
counted **for the team you are currently working in** — see
[Teams](help:teams) if the numbers look lower than you expect.

![The overview dashboard](screenshot:dashboard)

## Quick actions

The buttons across the top jump straight to the things people do most often:
**Bulk Upload Content**, **Add Content** and **Add Playlist**. You'll only see
the ones you have permission to use.

## Getting started

A short list of the first things to do, each linking to the page that explains
it. Handy for anyone new to the system, and safe to ignore once you know your way
around.

## The four counters

| Counter | What it counts |
|---|---|
| **Screens** | Physical displays in your team, and how many are online right now |
| **Content Items** | Images, videos and web pages in your team |
| **Playlists** | Playlists in your team |
| **Schedules** | Schedules in your team |

Each one is a link to the full list.

## Screens by status

Your displays split three ways. Displays check in by themselves every few
seconds, so this is close to real time.

- **Online** — checked in within the last {{ config.SCREEN_OFFLINE_AFTER }}.
- **Needs attention** — not checking in, but not confirmed dead. Usually a
  display that is powered on and on the network while whatever should be showing
  your content has stopped.
- **Offline** — not checking in, and nothing suggests it is alive. Switched off,
  disconnected, or registered against the wrong address.

The middle slice is the useful one: it separates the faults you can fix by
restarting a display from the ones needing someone to go and look at the
hardware. [Managing screens](help:screens) explains each state and what causes
it.

## Content by type

A breakdown of your content into **Image**, **Video** and **Website**. Mostly
useful as a sanity check — if you expected to see videos and the count is zero,
they didn't upload.

## Screens needing attention

Up to five screens that aren't reporting, each with the reason and how long it
has been that way. Each name links to that screen so you can check its settings.

Screens needing attention are listed **before** offline ones, even though a
screen that has been dark for days sounds worse. That's deliberate: a display
that is alive but not showing content is usually a quick fix and worth doing
first, while one that has been dark since Tuesday is a known problem that isn't
getting any worse.

If this panel says **All screens are online**, every display in your team is
reporting normally.

!!! tip
    A screen that has *never* been seen since it was created shows here too. That
    normally means the address recorded against it doesn't match the device — see
    [Managing screens](help:screens).

## Recent actions

Your own recent changes, newest first. Useful for retracing your steps — click
any entry to reopen what you edited.
