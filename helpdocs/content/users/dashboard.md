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

## Screens online vs offline

A screen counts as **online** if it has checked in within the last
{{ config.SCREEN_OFFLINE_AFTER }}. Displays check in by themselves every few
seconds, so this is close to real time.

A screen showing as offline usually means one of:

- the display is switched off, or its browser has been closed;
- the device has lost its network connection;
- the device is on, but has been given a different network address than the one
  registered against it.

## Content by type

A breakdown of your content into **Image**, **Video** and **Website**. Mostly
useful as a sanity check — if you expected to see videos and the count is zero,
they didn't upload.

## Offline screens

The five screens that have gone longest without checking in, with how long it's
been. Each name links to that screen so you can check its settings.

If this panel says **All screens are online**, every display in your team is
reporting normally.

!!! tip
    A screen that has *never* been seen since it was created shows here too. That
    normally means the address recorded against it doesn't match the device — see
    [Managing screens](help:screens).

## Recent actions

Your own recent changes, newest first. Useful for retracing your steps — click
any entry to reopen what you edited.
