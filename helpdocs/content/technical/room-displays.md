# Room and building displays

Room displays show **bookings**, not advertising content. They're driven straight
from the room calendars in Outlook, so there are no playlists or schedules
involved — you configure the room, and the display follows. Nothing on this page
overlaps with content, playlists or screens; that is a separate pipeline
entirely.

There are three kinds:

| Kind | Typical use |
|---|---|
| **Room** | A tablet or small screen outside a single room |
| **Building** | A foyer display covering every room in a building |
| **Room group** | A foyer display covering a chosen subset of rooms |

## Two ways to lay out a display

Buildings and room groups can be shown in either of two layouts:

- **Grid** — an hour-by-hour timetable, with a column per hour and a row per
  room. Best for planning at a glance.
- **Foyer** — a summary list of what's on, paging through if there's more than
  fits. Best for readability from a distance.

![A building grid display](screenshot:building-grid)

Set the **Default display** on the building or group. A single room always uses
the room layout.

## Setting up a building

1. Go to **Buildings** and choose **Add building**, or open an existing one.
2. Set the **Name**.
3. Under **Display**:
    - **Default display** — Grid or Foyer.
    - **Grid start hour** and **Grid end hour** — the span of the day shown on
      the timetable, on a 24-hour clock. The default 8 to 18 gives a ten-hour
      day. A narrower range gives each booking more room; **anything outside the
      range is cut off**, so make sure it covers your real booking hours.
    - **Pagination duration** — how long each page is held before moving to the
      next.
4. Under **Screensaver**, optionally enable it and set how long it shows for.
5. Save.

The **Grid** and **Foyer** buttons on the buildings list open the live display,
so you can check your changes immediately.

## Setting up a room

1. Go to **Rooms** and choose **Add room**, or open an existing one.
2. **Name** is the room's official name from Outlook, and is kept up to date
   automatically. Don't fight it.
3. **Display name** is yours to set. Fill this in when the official name is
   unhelpful — *Seminar Room 2* rather than *LIB-2F-SR02-40seat*. Leave it blank
   to use the official name.
4. **Building** — which building the room belongs to.
5. **Calendar address** is the room's Outlook mailbox. This is what pulls in the
   bookings. Leave it blank for a room whose bookings you manage by hand.
6. **Allow booking** lets people book the room from the display itself — see
   [Booking a room from its screen](help:booking-a-room).
7. Set **Pagination duration** and the **Screensaver** options as for a building.
8. Save.

![A room's settings](screenshot:room-form)

## Grouping rooms together

A **room group** is a chosen subset of one building's rooms — the three seminar
rooms on one corridor, say, rather than the whole building.

1. Go to **Room Groups** and choose **Add room group**.
2. Set the **Name** and choose the **Building**.
3. Move the rooms you want into the selected list.
4. Set the display and screensaver options as for a building.
5. Save.

!!! note "Groups can't span buildings"
    Every room in a group must belong to the group's building. Rooms from other
    buildings aren't offered, and if a room is later moved to a different
    building it drops out of the group automatically.

## The screensaver

With the screensaver enabled, the display alternates between the bookings and a
plain image. Content shows for the **pagination duration**, the screensaver shows
for the **screensaver duration**, then it repeats.

This is mainly there to protect displays that show the same thing all day.

## Private bookings

Bookings marked private or confidential in Outlook don't show their subject on
the display. The organiser's name is shown instead, so the room still reads as
occupied without revealing what for. This is automatic and can't be overridden
per room.

## Getting a display working

Configuring a room, building or group doesn't by itself make any physical screen
show it — the device has to be registered by IP as well. See
[Commissioning a display](help:device-commissioning).

If bookings aren't arriving at all, the room's mailbox is the place to look —
see [O365 rooms](help:o365-rooms).
