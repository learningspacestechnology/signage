# Where a screen is

Recording which building, and usually which room, each screen sits in, so you
can filter the screen list by campus or building and see every screen in a
building on one page.

For adding a screen and reading its status, see [Screens](help:screens).

## The room list comes from the University, not from here

The campuses, buildings and rooms you pick from are a copy of the University's
Learning Spaces record, refreshed automatically overnight. You choose from them;
you cannot add to them or correct them here.

That is deliberate — anything typed into those records would be overwritten by
the next refresh. If a room's name is wrong it has to be fixed at the source; ask
whoever administers this system to raise it with Learning Spaces Technology.

The list covers the **whole estate** — a few thousand rooms, teaching and
otherwise — and uses the internal campus names, so you will see Central North,
Central South and Central West rather than one "Central".

!!! note "The room list is not filtered to your team"
    Every team's screens sit in the same real buildings, and a screen you are
    commissioning is usually going into a room that has no screen in it yet — so
    the picker offers every catalogued room, not just the ones your team already
    uses. Your **Screens** list is still only ever your own.

    If your account is limited to particular **locations**, though, the picker
    offers only the buildings and rooms in them. See [Teams](help:teams).

## Setting a screen's room

Choosing a room takes two steps: the building, then the room in it.

1. Open the screen from the **Screens** list.
2. In the first block of fields, click the **Building** box and start typing
   the building's name. Buildings are grouped under their campus.
3. Click the **Room** box. It now lists only that building's rooms; type to
   narrow them down.
4. Pick the room and save.

The building is saved along with the room. If the screen is somewhere in the
building that isn't a catalogued room, stop after step 2. See
[A screen in a building but not in a room](#a-screen-in-a-building-but-not-in-a-room)
below.

The **Room** box stays greyed out, reading *Choose a building first*, until a
building is chosen. Changing the building empties the room, so you never end up
with a room from the building you have just moved away from.

Each room is shown with the University's reference for it in brackets, for
example **1.1 (1gs1.1)**. The name alone is not always enough: the University's
record holds a few rooms twice under the same name, and the reference is how you
tell them apart. If you are unsure which of two is right, either will place the
screen in the correct building; ask whoever administers this system to report the
duplicate so it can be fixed at the source.

To take a screen out of a building altogether, clear the **Building** box (the
× at its right) and save. That clears the room too. Leave both blank only when
you don't know where the screen is yet; it then appears under **No location
set** until someone places it.

## A screen in a building but not in a room

The University's record lists teaching and bookable rooms, but it rarely lists
entrance halls, foyers, corridors or window displays, and those are where many
screens are. For a screen like that, choose the **Building**, leave **Room**
blank, and save.

The screen then:

- appears under that building in the **Campus** and **Building** filters, on
  the dashboard's **Screens by building** panel, and on the building's own
  screens page, where its room reads **No room**;
- shows a dash in the **Room** column of the **Screens** list;
- is found by the **Room → In a building, no room** filter, and is *not*
  counted as unplaced.

Check the **Room** box first, though. A few foyers and atriums *are*
catalogued, for example "Concourse" or "Usher Foyer One". If yours is, pick
it, because a room gives the screen more detail than a building does.

If your account is limited to particular locations, you can only leave **Room**
blank in a building you have access to **as a whole**. If you were given access
to particular rooms in the building, you can choose the building, but saving
without a room is refused with *Choose a room. Your locations include rooms in …
but not the whole building*. A screen with no room in that building would be
outside your locations, so it would vanish from your list as soon as you saved
it. Ask someone with access to the whole building to look after it, or ask an
administrator to extend your locations. For the same reason, the **Building**
box is always required for you.

!!! warning "\"The results could not be loaded\" means a missing permission"
    If you can choose a building but the **Room** box then says *The results
    could not be loaded*, you have not been granted permission to read the room
    directory. It is a separate permission from editing screens. Ask an
    administrator to add it.

## Filtering the screen list

Once screens have buildings, the **Screens** list gains three more filters:

- **Campus**
- **Building** — once you choose a campus, this lists only that campus's
  buildings. Switching to another campus clears a building that is not on it,
  so you never end up with an empty list from a building and campus that
  cannot both match.
- **Support type** — who the University's room record says looks after the
  room. **Not recorded** finds screens in rooms with no support type set, which
  is common; a screen with no room at all is not included.

Like the **Schedule** filter, they only offer values that are actually in use by
screens you can see, so an option here always returns something. Two consequences
worth knowing:

- A building where none of your screens sits is not offered. That is not a fault.
- Until you have placed at least two screens in different buildings, the
  campus and building filters do not appear at all — there is nothing yet to
  choose between. The support type filter appears once any of your screens is in
  a room with a support type.

There is also a **Room** filter with four options:

- **In a room**
- **In a building, no room** — screens placed in a building but not in a
  catalogued room, such as a foyer.
- **No location set** — the commissioning backlog: screens with neither a
  building nor a room, still waiting to be placed. Not offered if your account
  is limited to particular locations, since you never see such a screen.
- **In an inactive room** — screens whose room is not open today. See
  [Inactive rooms](#inactive-rooms) below.

The **Building** and **Room** columns show where each screen is. A dash in
**Room** alone means the screen is in the building but not in a catalogued
room; a dash in both means it hasn't been placed.

![The screens list, showing the building and room columns](screenshot:screen-list)

## Every screen in a building

From **Estate directory → Estate buildings**, the **Screens** button on a
building opens a page listing every screen in it, with the same status badges as
the main list, plus something the screen list cannot show you: **the rooms in
that building with no screen**.

That second list is the useful half. It answers "what have we not covered yet"
rather than "what have we covered".

Screens placed in the building with no room are listed first, with **No
room** in the Room column. They don't count as covering any room, so they never
take a room off the second list.

![Every screen in one building](screenshot:estate-building-screens)

Both halves are scoped to your team, which is why the heading says "no screen
**you can see**" — a room listed there may well hold another team's display. If
your account is limited to particular locations, both halves also cover only
your rooms, and a building outside your locations cannot be opened. Screens with
no room appear only if you have access to the whole building.

Rooms that are not open today carry an **Inactive** badge in both halves.
They are still listed: a room that opens next month may be waiting for its
screen.

The same page is reachable from each building row on the
[dashboard](help:dashboard).

!!! tip
    **Open in screen list** at the top right takes you to the ordinary
    **Screens** list, filtered to that building, where the usual sorting and
    bulk actions are available.

## Inactive rooms

The University's record says, for each room, whether it is **open today** —
worked out from the dates the room comes into and goes out of use. A room
outside those dates is **inactive**: closed for refurbishment, decommissioned,
or not open yet.

A screen in an inactive room gets an **Inactive** badge beside its room name,
on the **Screens** list and on the building's screens page. To list them all,
filter the **Screens** list by **Room → In an inactive room**.

The badge is a prompt to check, not an error. Nothing stops working, and the
screen keeps its room. Usually one of these is true:

- **The room really is closed.** Move the display, or leave it if it is
  deliberately showing something to people passing by.
- **The screen is in the wrong room.** Set the room it is actually in.
- **The room has not opened yet.** Leave it; the badge goes once the room's
  start date arrives and the overnight refresh has run.

Inactive rooms can still be picked in the **Room** box, for that last reason.
If the University's dates for a room look wrong, it has to be fixed at the
source — ask whoever administers this system to raise it.

## When something looks wrong

**A building is missing from the filter.** It has no screens you can see in it,
or a campus is selected and the building is on a different one — set
**Campus** back to **All**. Otherwise, place a screen in it and it appears.

**A room is missing from the picker.** First check the **Building** box: the
**Room** box only lists rooms in the building chosen there. If your account is
limited to particular locations, the room may be outside them. Otherwise, either
the overnight refresh has not run since the room was added to the University
record, or it is not in that record at all. An administrator can trigger a refresh from **Estate directory → Estate
rooms**. If the room genuinely isn't catalogued, choose the building and leave
**Room** blank — that is a supported state. See
[A screen in a building but not in a room](#a-screen-in-a-building-but-not-in-a-room).

**A screen's room says "Missing"** on the room record. The University has stopped
publishing that room — usually a decommission or a renumbering. The screen keeps
working and keeps its room; nothing is deleted out from under you. Check whether
the display should move, and set the new room when you know it.
