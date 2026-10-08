# The estate directory

A local copy of the University's Learning Spaces record — every campus,
building and room across the estate, a few thousand of them, refreshed
nightly. Screens are assigned to rooms from it, which is what
lets the screen list be filtered by building and the dashboard report status per
building.

For the operator's view of assigning a screen to a room, see
[Where a screen is](help:users/screen-locations).

!!! warning "This is not the same as Buildings and Rooms under Room Schedules"
    Two different things share those words, and confusing them wastes an
    afternoon.

    **Estate buildings and Estate rooms** are a read-only copy of the
    University's record — every room it holds, teaching or not, equipped or
    not. You cannot edit them.

    **Buildings and Rooms** under *Room Schedules* are display configuration —
    one is created when an operator assigns an Outlook room mailbox, and it
    carries layout and screensaver settings for a booking display. See
    [Room and building displays](help:room-displays).

    They can be linked to each other, but they are separate records with
    separate purposes.

## Where the data comes from

A nightly task reads the room list from the Learning Spaces Datastore at
`{{ config.LSD_API_BASE_URL }}` and mirrors it locally. It runs
{{ config.ESTATE_SYNC_SCHEDULE }}.

It reads a feed the Learning Spaces team publishes specifically for this system,
in pages of a thousand rooms. The whole list is collected before anything is
written, and the run is abandoned — and retried — if the pages do not add up:
if the total the datastore declares changes part-way through, if the rooms
collected fall short of it, or if a room turns up twice. Those are the signs of
the list changing under the read, and acting on a half-read list could delete
rooms that still exist.

**Scope: the whole estate.** Every room the datastore holds is imported —
teaching space, study space, meeting rooms, specialist rooms and everything
else — and the campus names are the internal ones the Learning Spaces team
uses, so Central appears as Central North, Central South and Central West
rather than being flattened into one.

The feed is a flat list of rooms; each row names its campus and building as
plain text. There is no separate buildings or campuses feed, so **buildings and
campuses here are derived** from the distinct values across the room list. That
has consequences worth knowing, below.

!!! note "Much of it is sparsely filled in"
    Capacity is set on under a third of rooms, coordinates on about the same,
    a service provider on well under half. That is the state of the source
    data, not a sync fault. Blank means "not recorded upstream".

Access needs an API key, which an administrator sets in the deployment
configuration. Without one the sync refuses to run and logs why; nothing else in
the system is affected.

## Why you cannot edit any of it

The three lists open read-only, for everyone including superusers. An edit made
here would survive exactly until the next nightly run and then vanish without
warning, so the form does not offer to save.

A wrong room name, a missing room, a room in the wrong building: all of those
have to be corrected at the source. Contact Learning Spaces Technology.

## Running a sync by hand

**Estate directory → Estate rooms** carries a **Sync estate now** button, for
users who can see all locations. Use it
after a room has been added upstream and you do not want to wait for the night.
A full run takes a few seconds.

It queues a background job rather than running in the page, so the list will not
change until the worker finishes — usually a couple of minutes. Repeated presses
within a minute are ignored.

![The estate rooms list](screenshot:estate-room-list)

## How campuses and buildings are worked out

**Campuses** are identified by their internal name, and each carries a short
code (CN, KB, HR and so on) as a label. The code is deliberately *not* the
identifier: it arrives in mixed case, missing on a few rows, and with at least
one code used for two different campuses — so it is resolved by majority and
shown, not trusted.

**Buildings** are identified by their campus and their name together. The
campus has to be part of it because one building name — Medical School —
genuinely exists on two campuses.

**Estates building codes** — the building numbers Estates uses, such as 0228 —
come with each room, but they are *not* how buildings are identified. They are
Estates' own grouping and do not line up one-to-one with building names here:
one building can carry several codes, one code can cover two buildings that are
named separately here (40 George Sq and its Lower Hub, for instance), and
buildings the University does not own have none.

The **Estate buildings** list shows every code a building's rooms carry, and
can be sorted by them — a building with several sorts by its lowest. To see
everything Estates files under one code, either use the **Estates building
code** filter on that list, or search the estate building or room list for it.
Filtering lists each building once, however many of its rooms carry the code.
A building with no code shows a dash.

Each room also carries a **public campus** — the broader grouping used on the
public website ("Central" covers Central North, South and West). It is shown
for reference only; it is missing on nearly half of rooms upstream and is not
used to place anything.

The practical consequences:

- **A building is renamed upstream.** It is treated as a new building, and the
  old one disappears once nothing is left in it. **Screens keep their rooms**
  either way: rooms are matched on the datastore's own room id, so only the
  building record changes underneath them, and each screen's building follows
  its room in the same refresh. The exception is a screen placed in the
  building **with no room**: it has nothing to follow, so it stays on the old
  building, which is kept and marked **Missing**. Move such screens to the new
  building by hand.
- **A room moves to a different building.** It is simply re-pointed, keeping
  its record and any screen in it.
- **Two buildings share a name on one campus.** They would be merged. That does
  not happen in the current data; if it starts to, it needs a code upstream.

## When a room disappears from the feed

Rooms are matched on the datastore's own room id, so a rename never loses one.
When a room stops being published at all — a decommission, usually — one of two
things happens:

- **Nothing points at it.** The record is deleted.
- **A screen, a display room or a location group points at it.** The record is
  kept and marked **Missing**, and the thing pointing at it is untouched.

The same goes for a building a screen is placed in, and for a building or
campus a location group grants. A grant on a
building that has been *renamed* upstream is kept but covers nothing, so it is
flagged for review — see [Location access](help:location-access).

That asymmetry is deliberate: a screen must never silently lose its location
because of an upstream change. Filter the estate room list by **Missing** to see
what needs attention.

!!! note "A shrinking feed is treated as a fault, not a fact"
    If the feed comes back drastically smaller than the rooms already held, the
    sync applies the updates it received but **deletes and flags nothing**, and
    logs the refusal. Refusing to delete is recoverable; deleting the estate
    and unlinking every screen is not. If the room list stops shrinking when
    you expect it to, check the task log.

    This sits behind the page-count check above. That check catches a list
    that was cut short in transit; this one catches a list that is complete by
    its own count but wrong — filtered by mistake upstream, say.

## Linking display rooms to the estate

**Estate directory → Link display rooms** (also the **Estate links** tab on the
O365 rooms pages) ties each *Room Schedules* building and room to its estate
record.

Buildings first, rooms second. Until a display building is linked, its rooms are
listed but offer no suggestions — room labels like "2.14" only become unambiguous
inside a building, so matching them across the whole estate would produce
confident nonsense.

Suggestions are labelled with how they were found — **Exact name**, **Room
number**, **Strong**, **Possible** — and **none is pre-selected**.
Confirm one, or use the full list beside it. Nothing is ever linked
automatically.

![Linking display rooms to the estate](screenshot:estate-room-links)

Each estate room can back only one display room; trying to reuse one says so and
names the room already holding it.

## Permissions

Reading the three lists needs **estate | Can view campus / estate building /
estate room**. Making links needs **room schedules | Can change room**, and the
ability to see all locations.

The lists are also limited by [location groups](help:location-access): a user
limited to some places sees only those campuses, buildings and rooms, and counts
cover only what they can see. The linking page, the link lists and **Sync estate
now** draw on the whole estate, so they are not available to such a user at
all.

!!! warning "Grant the view permissions alongside screen editing"
    The **Room** picker on a screen reads the estate room list, so a user who can
    edit screens but has not been granted **Can view estate room** can choose a
    building and then gets *The results could not be loaded* in the **Room**
    box, with no mention of permissions. Add the estate view permissions to
    whichever group already holds screen editing. (The **Building** box beside
    it needs no permission of its own.)

## What a display device is told

The player's regular check-in includes a `room` object naming the room, its
building and campus, its status, capacity, whether it is open today,
coordinates, and a `support` block with the service provider and VoIP number —
or `null` for a screen with no room.

**Nothing on the display uses it yet.** It is sent so that a future player build
can show where it is, or offer wayfinding, without a change here first. It does
not affect the publish timestamp, so it cannot cause a screen to restart its
rotation. Do not go looking for an on-screen feature; there isn't one.

See [The player API](help:player-api) for the rest of that payload.

## Open today

Each room is either **open today** or **inactive**. The datastore works this
out from the dates the room comes into and goes out of use — dates it does not
publish, so they cannot be checked from here. A room with no dates counts as
open. Because the answer depends on today's date, a room can change state
overnight with no edit upstream; here it changes at the next sync.

Filter the estate room list by **open today** to see the inactive ones. A
screen in an inactive room is flagged for operators — an **Inactive** badge
beside its room, and a **Room → In an inactive room** filter on the screen list
— but nothing is hidden or unlinked. An inactive room can still be picked,
because a room that opens next month may rightly get its screen now. The
"Inactive rooms" section of [Where a screen is](help:users/screen-locations)
covers the operator's side.

The status column (General Teaching, Specialist, Not in use and so on) is a
separate record kept by hand upstream. The two do not always agree — a few
rooms are "Not in use" yet open today. Trust **open today** for the flag;
raise disagreements with Learning Spaces Technology.

## Support information

Each room carries whoever looks after it: **support type**, **service
provider** and a **VoIP number** for the room's phone where there is one. The
estate rooms list can be filtered by support type.

All three are blank on a good number of rooms — that is the source data, not a
fault. The feed does not carry the support *group* (the school or service that
owns a room), so that is not available here.

The room page also shows the **Optime index** where there is one: the
timetabling system's own id for the room, kept so the two can be matched later.
