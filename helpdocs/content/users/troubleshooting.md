# Something isn't showing on a screen

This page is organised by what you're seeing, not by feature. Start with the
symptom that matches.

## The screen is blank, or stuck on one thing

**Check the screen's status.** Go to **Screens** and read the **Status** and
**Detail** columns. If it isn't **Online**, the display isn't reaching the system
at all — the content is not the problem. See
[the status checklist](#a-screen-isnt-reporting) below.

**Check the schedule is pointing somewhere sensible.** Open the screen, note its
schedule, and open that. Does its default playlist have content in it? Is a rule
active right now that points at an empty playlist?

**Preview it.** Open the screen and scroll to **Preview**. If the preview shows
the right thing but the display doesn't, the problem is at the display, not in
your configuration.

!!! note "One item held for a long time is normal"
    A playlist with exactly one piece of content holds it for an hour instead of
    cycling. If a screen looks frozen but is showing the correct single item,
    that's working as intended.

## A specific item isn't playing

Work down this list:

1. **Is it in the playlist?** Open the playlist and check the entries. Being in
   *Content* isn't enough.
2. **Is that playlist actually playing?** Check the screen's schedule — a rule
   may be showing a different playlist at this time of day.
3. **Has it started yet?** If **Valid from** is in the future, it's waiting.
4. **Has it expired?** If **Expires at** has passed, it has stopped playing and
   may already have been deleted.
5. **Is it a website that won't embed?** Some sites refuse to be displayed inside
   another page. Open the address in a browser tab to check — if it works there
   but not on screen, the site is blocking it and you'll need different content.

## My change hasn't appeared

Give it a couple of minutes. Screens check for updates on their own; you don't
have to publish anything.

- Editing a playlist's entries takes effect within about a minute.
- Content whose start date has just passed is picked up by a job that runs
  {{ config.CONTENT_TASK_MINUTES }}.
- Renaming content changes nothing on screen — the name is only ever seen by you.

If it still hasn't appeared after five minutes, confirm the screen is online and
use **Preview** to see what the system thinks it should be showing.

## The screen says it isn't configured

The display is working and can reach the system, but the system doesn't recognise
its network address.

That page prints the device's address on screen. Read it off, then either:

- add a new screen using that address — see
  [Managing screens](help:screens); or
- open the existing screen record and correct its address, if the device's
  address has changed.

## A screen isn't reporting

Read the **Detail** column first. It tells you which of these you are dealing
with, and they call for completely different things.

### "Stopped reporting recently"

It missed its last check-in and nothing more. Wait a minute and reload before
doing anything — a display that restarts briefly looks exactly like this.

### "Responds to ping but is not reporting"

The device is powered on and on the network. What has stopped is the software
showing your content, almost always the browser. In order:

1. **Restart the display.** This fixes the large majority: a crashed browser, a
   closed window, an error page, or a page sitting on old content with its
   scripts stopped.
2. **Check what's actually on the screen.** An error page or a stale image tells
   you it never recovered from something; a black screen with the device
   powered on usually means the browser isn't running at all.
3. **If it comes back and goes again**, open the screen and look at its status
   history under **Status**. A screen flapping every few minutes is a different
   problem from one that failed once — mention that when you report it.

### "No contact", or "No contact and no ping response"

Nothing suggests the device is alive. In rough order of likelihood:

1. **The display is off, asleep, or unplugged.** Check it physically.
2. **Its address has changed.** If the display is showing the "not configured"
   page, this is what happened. Read the new address off the screen and update
   the record.
3. **It's lost network connectivity.** Nothing you can fix from here — ask
   whoever looks after the network.

!!! note
    "No contact" without the ping part means nobody has checked whether the
    device is reachable, so a display with a dead browser will show here rather
    than as needing attention. See [Managing screens](help:screens).

## An upload was rejected

| Message | Fix |
|---|---|
| Video files must have `.mp4` extensions | Convert the video to MP4 and upload again |
| Image resolution must be at most {{ config.MAX_IMG_WIDTH }}×{{ config.MAX_IMG_HEIGHT }} | Resize the image before uploading |
| File cannot be blank for image or video type | Choose a file, or switch the type to Website and enter an address |

## I can't find something a colleague made

Almost always [teams](help:teams). You're looking at one team's items; theirs is
in another. Ask which team it belongs to, switch to it using the team name at the
top of the page, or ask an administrator to add you to it.

## My screen list is empty, or a screen has gone missing

If the dashboard says you do not have access to any locations, your account has
not been given any places yet. Ask an administrator to add you to a location
group.

Otherwise the screen is probably in a room outside your locations, or belongs to
another team. See *Your locations* in [Teams](help:teams).

## A playlist won't let me pick another playlist to inherit from

Either it would create a loop — following the chain would lead back to the
playlist you're editing — or the other playlist belongs to a team you're not in.
See [Sharing content between playlists](help:playlist-inheritance).

## A building is missing from the campus or building filter

It isn't a fault. Those filters only offer buildings that hold a screen **you**
can see, so a building with none of your screens in it is left out — as is a
building holding only another team's displays.

For the same reason, neither filter appears at all until your screens are spread
across more than one building.

If a screen genuinely is in that building, set its **Building** (and its
**Room**, if it is in a catalogued one); the building appears as soon as you
save. See [Where a screen is](help:screen-locations).

## A room is missing from the Room picker

The room list is a copy of the University's own record, refreshed overnight. It
covers the whole estate, so most rooms are in it — but it cannot be added to
here.

The **Room** box only lists rooms in the building chosen in the **Building** box
above it, so check that first. Buildings are grouped under the internal campus
names, so look under "Central North" rather than "Central".

Otherwise, a missing room usually means it is newer than the last overnight
refresh, or that it simply isn't catalogued, which is usual for foyers and
entrance halls. Ask an administrator to run a refresh; if it still isn't there,
choose the **Building** and leave **Room** blank. That is a supported state, not
a gap to be filled.

If the **Room** box says *The results could not be loaded* for every building,
that is a different problem: you have not been given permission to read the room
list. Ask an administrator.

## A room display is showing the wrong bookings, or none

Room displays are driven from the room calendars in Outlook, not from playlists
or schedules, so nothing on this page applies to them and there is nothing you
can change here to fix one.

Report it to your administrator. Say which room, what the screen shows, and what
Outlook shows — that is what they'll need.

## Still stuck

Note down:

- the screen's name and its address;
- what it's showing versus what you expected;
- when you made the change.

Then contact your administrator. Those three things answer most of the questions
they'll ask.
