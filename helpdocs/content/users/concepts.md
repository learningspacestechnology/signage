# How it all fits together

There are four building blocks. Once you know what each one does, everything
else in {{ config.ADMIN_SITE_NAME }} follows.

```
Content  →  Playlist  →  Schedule  →  Screen
```

Read that right to left when you're planning: *this screen* follows *this
schedule*, which picks *a playlist*, which is a list of *content*.

## The four building blocks

### Content

A single thing that can be displayed: an image, a video, or a live web page.
Content on its own is never shown anywhere — it has to be in a playlist.

Content can have a **start** and **end** date, so a poster for an event can
appear a week before and disappear afterwards without you doing anything.

→ [Adding and managing content](help:content)

### Playlist

An ordered list of content, with a display time for each item. A playlist is what
actually plays: item 1, item 2, item 3, back to item 1.

Playlists can also **inherit** from other playlists, so shared announcements only
have to be maintained in one place.

→ [Building playlists](help:playlists) ·
[Sharing content between playlists](help:playlist-inheritance)

### Schedule

A set of rules that decides *which playlist is playing right now*. A schedule
always has a **default playlist**, plus any number of rules such as "show the
Open Day playlist on Mondays and Wednesdays between 09:00 and 17:00".

If no rule matches the current moment, the default playlist plays.

→ [Scheduling what plays when](help:schedules)

### Screen

A physical display. Each screen is recognised by its network address and points
at one schedule. Screens also report in regularly, which is how the system knows
whether one is online.

→ [Managing screens](help:screens)

## A worked example

Say you look after a foyer display.

1. You upload three posters as **content**.
2. You put them in a **playlist** called *Foyer Rotation*, 15 seconds each.
3. You create a **schedule** called *Foyer* whose default playlist is
   *Foyer Rotation*. You add one rule: during Open Day week, show the
   *Open Day* playlist instead.
4. You add a **screen** called *Foyer Display* and point it at the *Foyer*
   schedule.

From then on the screen shows your three posters, and automatically switches to
the Open Day playlist for that week without anyone touching it.

## Two things that cut across everything

### Teams

Every piece of content, playlist, schedule and screen belongs to one or more
**teams**. You only see the ones belonging to your team. This is why a colleague
in another department can't accidentally change your screens — and why their work
doesn't show up in your lists.

→ [Teams and what you can see](help:teams)

### Room displays are separate

Screens that show **room bookings** — a tablet outside a meeting room, a
timetable grid in a foyer — do not use content, playlists or schedules at all.
They're driven directly from the room calendars, and are set up and looked after
by technical staff.

Nothing on these pages applies to them. If a room display is wrong, contact your
administrator rather than looking for a playlist.

## How quickly do changes appear?

You don't need to do anything to "publish". Screens check for changes on their
own:

- Edit a playlist, and screens using it pick the change up within about a minute.
- Content whose start date has just passed is brought in by a background job that
  runs {{ config.CONTENT_TASK_MINUTES }}.
- Room displays notice booking changes within about ten seconds.

If a change still isn't showing after a few minutes, see
[Something isn't showing on a screen](help:troubleshooting).
