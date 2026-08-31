# Managing screens

A **screen** is a physical display. Each one is recognised by its network
address, and follows one schedule.

{% if perms.screens.add_screen %}
## Adding a screen

You'll need the display device's **IP address** before you start. If you don't
have it, the device itself will tell you — see
[Getting the address off the device](#getting-the-address-off-the-device).

1. Go to **Screens** and choose **Add screen**.
2. Give it a **Name**. Use something a colleague would recognise from standing in
   the building — *Library Entrance*, not *Screen 3*.
3. Choose the **Schedule** it should follow. See
   [Scheduling what plays when](help:schedules).
4. Enter the **IP** address of the device.
5. Optionally set an **Interspersed playlist** and **rate** — a playlist mixed
   into whatever this screen is showing, whichever playlist that is. See
   [Interspersed content](help:playlists).
6. Save.

![Adding a screen](screenshot:screen-form)

Within a minute or so the display should start showing content, and the screen
should show as online.
{% endif %}

{% if perms.screens.change_screen %}
!!! note "Saving a screen restarts its display"
    Any change you save here — even just the name — makes that display reload
    and begin its playlist again from the first item. It takes a couple of
    seconds and nothing is lost, but don't be surprised if you're watching the
    display while you edit it.
{% endif %}

## Getting the address off the device

A display that isn't registered yet shows a **"screen not configured"** page
instead of content, and that page prints the device's own network address and
name on screen.

Walk up to the display, read the address off it, and use that when adding the
screen. You don't need to look anything up on the network.

## Screen status

The **Screens** list shows a status for each screen, the reason behind it, and
when the display was last heard from.

![The screens list, showing each screen's status](screenshot:screen-list)

Displays check in by themselves every few seconds. There are three states:

| Status | What it means | Where to look |
|---|---|---|
| **Online** | Checked in within the last {{ config.SCREEN_OFFLINE_AFTER }}. | Nothing to do. |
| **Needs attention** | Not checking in, but not confirmed dead either. | Usually the display's software. |
| **Offline** | Not checking in, and nothing suggests it is alive. | Power, network, cable. |

The **Detail** column always says which of these applies and why, so you never
have to work it out from the colour:

- **Responds to ping but is not reporting** — the device is powered on and on
  the network, but the thing that should be showing your content isn't running.
  Nearly always the browser: it has crashed, been closed, shows an error page,
  or is sitting on a cached page with its scripts stopped. Restarting the
  display fixes most of these.
- **Stopped reporting recently** — it missed its last check-in but only just.
  Wait and reload before chasing it; a display briefly restarting looks exactly
  like this.
- **No contact and no ping response** — the system asked and got nothing back.
- **No contact** — it isn't checking in, and nothing has asked whether it is
  reachable. See [Reachability checks](#reachability-checks) below.

!!! note "Amber depends on a setting"
    "Responds to ping but is not reporting" only ever appears when reachability
    checking is turned on, which is a system-wide setting.
{% if config.SCREEN_PROBE_ENABLED %}    It is turned on here.
{% else %}    It is **turned off** here, so screens move straight from
    "stopped reporting recently" to offline. Ask whoever administers the system
    if you'd like it on.
{% endif %}

A screen that is offline is usually:

- switched off, or its browser has been closed;
- disconnected from the network;
- on an address that has changed and no longer matches what's registered here.

The last one is the most common and the least obvious. If a display is clearly
powered on and showing the "not configured" page, its address has changed — read
the new one off the screen and update the record.

### Reachability checks

When it is turned on, the system quietly asks each non-reporting screen whether
it is still on the network, {{ config.SCREEN_CHECK_SCHEDULE }}. That is what
separates **needs attention** from **offline**, and it is the difference between
restarting a browser and walking over with a spare cable.

A successful check keeps a screen amber for {{ config.SCREEN_PING_WINDOW }}. If
it stops answering as well as not reporting, it turns red.

### Status history

Open a screen and look under **Status** for its recent changes — when it went
dark, when it came back, and why. Kept for {{ config.SCREEN_HISTORY_DAYS }} days,
except that a screen's most recent change is never removed, so "offline since
last Tuesday" stays answerable however long it has been.

## Previewing a screen

Open the screen and scroll to **Preview** for a live view of exactly what it is
showing right now, embedded in the page. **View on site** opens the same thing
full size in a new tab.

This is the quickest way to confirm a schedule change did what you meant, without
walking to the display.

## Finding screens

On the **Screens** list you can search by **name or IP address**, and filter by:

- **Schedule** — useful for checking which displays are affected before you
  change a schedule. Only schedules actually in use by screens you can see are
  listed, so an option here always returns something.
- **Status** — narrows the list to **Online**, **Needs attention** or
  **Offline**. Filtering by **Needs attention** is the quickest way to find the
  displays worth walking to.

You can also sort by the **Status** column. It sorts by how bad things are
rather than alphabetically, so one click puts the healthy screens first and a
second click puts the problems at the top.

!!! note "The status filter is a snapshot"
    It uses the same rules as the **Status** column, worked out at the moment
    the page loads. Reload and a screen that has just checked in — or just
    stopped — moves between the options. Filter by **Offline**, then reload once
    before chasing anything: a display briefly restarting will have come back.

{% if perms.screens.change_ticker_text or perms.screens.change_ticker_settings %}
## Adding a message bar

Screens can show a scrolling message along the bottom, over or beside the normal
content. See [Adding a scrolling message](help:ticker-tape).
{% endif %}

{% if perms.screens.delete_screen %}
## Deleting a screen

Open the screen and use **Delete**, or tick it in the list and use the action
menu. Unlike content and playlists, the screen form does have a delete button.

Deleting a screen doesn't affect its schedule, playlists or content — only the
record of that display.
{% endif %}
