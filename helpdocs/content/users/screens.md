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

## Online and offline

The **Screens** list shows a tick or a cross for each screen, and when it was
last heard from.

Displays check in by themselves every few seconds. A screen counts as **online**
if it has checked in within the last {{ config.SCREEN_OFFLINE_AFTER }}.

A screen showing offline usually means:

- the display is switched off or its browser has been closed;
- it has lost network connectivity;
- its address has changed and no longer matches what's registered here.

The last one is the most common and the least obvious. If a display is clearly
powered on and showing the "not configured" page, its address has changed — read
the new one off the screen and update the record.

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
- **Online status** — narrows the list to the displays that are reachable, or to
  the ones that aren't.

!!! note "The online filter is a snapshot"
    It uses the same {{ config.SCREEN_OFFLINE_AFTER }} rule as the tick in the
    **Online** column, worked out at the moment the page loads. Reload and a
    screen that has just checked in — or just stopped — moves between the two.
    Filter by **Offline**, then reload once before chasing anything: a display
    briefly restarting will have come back.

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
