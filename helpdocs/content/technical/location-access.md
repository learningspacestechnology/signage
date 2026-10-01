# Location access

**Location groups** decide which campuses, buildings and rooms a person can see,
and so which screens. They are the third access layer, alongside teams and
permissions; [How access works](help:access-model) explains how the three fit
together. This page covers setting them up.

## What a location group grants

A location group is a named set of places plus a list of members. Each place
covers everything beneath it:

| Grant | Covers |
|---|---|
| **Campus** | Every building and room on it |
| **Building** | Every room in it, including rooms the overnight refresh adds later |
| **Room** | Just that room |

A room granted on its own also makes its building and campus visible, but not the
building's other rooms. Someone given only *Appleton Tower — LT2* sees Appleton
Tower and its campus in the estate lists, with LT2 as the only room in them.

Someone in several groups sees everything any of their groups grants.

### What it limits

For a user limited to location groups:

- **Screens** — the list, its filters, the dashboard counts and the per-building
  pages show only screens in their rooms. This is on top of teams: they see a
  screen only if it is in their active team **and** in one of their rooms.
- **Screens with no room** are hidden from them, because no grant can cover
  one. For the same reason, the **Room** field on a screen is **required** for
  them, and the **No room set** filter option is not offered.
- **Estate directory** — the campus, building and room lists, and the
  **Building** and **Room** boxes on a screen, offer only their places. Counts
  on those lists cover only what they can see.
- **Estate links, Link display rooms, Estate building/room links and Sync
  estate now** are not available to them, because each draws on the whole
  estate.

Content, playlists and schedules are not tied to a place and are unaffected.
So is everything under **Room Schedules**, including the O365 rooms pages.
Location groups do not restrict those yet.

## Who sees everything

**Superusers**, and anyone holding the permission **estate | location group |
Can see all locations**, are not limited at all.

That permission is handed out through the **All locations** group. When location
groups were introduced, every existing staff account was added to it, so nobody
lost access on the day. To limit someone to particular places, add them to one
or more location groups, **then** remove them from **All locations**.

!!! warning "No location group means no screens"
    A staff user with neither a location group nor **Can see all locations**
    sees **no screens at all**. They can still sign in and work with content,
    playlists and schedules, and their dashboard tells them they have no
    locations. This applies to every newly created account, including one
    created by a first Microsoft sign-in, so giving location access is part of
    onboarding, like choosing a team.

## Creating a location group

Location groups are superuser-only.

1. Go to **Users, Groups & Teams → Location groups** and choose **Add location
   group**.
2. Give it a **Name** that says what it covers ("Informatics buildings",
   "Library foyers"). A **Description** is optional.
3. Choose the places:
    - **Campuses**: tick any whole campuses.
    - **Buildings**: type to search; buildings are grouped by campus.
    - **Rooms**: type a room name, its datastore reference or its building
      name.
4. Add **members** using the member rows at the bottom.
5. Save.

![Editing a location group](screenshot:location-group-form)

### A whole building, or its rooms?

The **Add every room currently in** box is a shortcut. It adds each room those
buildings hold today to **Rooms** when you save. You can then remove the few you
don't want.

| | Granting the building | Adding its rooms |
|---|---|---|
| A room added upstream later | Covered automatically | Not covered |
| Excluding a few rooms | Not possible | Remove them from **Rooms** |
| Building renamed upstream | Grant needs re-pointing (below) | Unaffected |

Grant the building when the person looks after the whole of it. Add the rooms
when they look after most of it but not all.

## Giving someone access

There are three places to do it, and they all do the same thing:

- **On the location group**: add a member row.
- **On the user**: superusers see a **Location groups** block on each user's
  page.
- **When creating a user**: the add-user form has a **Location groups** field
  next to **Teams**.

The **Users** list has a **Locations** column showing *All locations*, the names
of a user's location groups, or *No access*. The **By location access** filter
finds each case. **No location access** finds the accounts that currently see
no screens.

## When the estate changes underneath a group

The overnight refresh never deletes a campus, building or room that a location
group grants. If the University stops publishing one, it is kept and marked
**Missing**, just as it is for a room a screen points at.

It still needs a person, though. The usual cause is a **building renamed
upstream**, which arrives as a *new* building, while the rooms move across to
it. A grant on the old building then covers nothing, and the group's members
quietly lose sight of those screens.

You are told in three places:

- The dashboard, for superusers: *"… location group grants a place the estate
  datastore no longer returns"*, with a link.
- The **Location groups** list: a **Needs review** column and filter.
- The group's own page, which lists the missing places, and marks them
  *(missing from datastore)* in the pickers.

To fix it, grant the new building and remove the old one. Room grants are not
affected by a building rename, because rooms keep their datastore reference.

## Who can change access

Only superusers can edit location groups and their members, just as only
superusers can manage teams.

!!! warning "Editing groups or users is close to superuser"
    Anyone holding **Can change group** or **Can change user** can put
    themselves, or anyone else, in the **All locations** group, or give the
    **Can see all locations** permission directly. They can also grant any other
    permission, so this is not new, but keep those two permissions to people
    you would trust with every location.

## When something looks wrong

**Someone sees no screens at all.** Check their **Locations** column in the
**Users** list. *No access* means they need a location group. If it names
groups, check the groups actually grant something: a group with only missing
places covers nothing.

**Someone sees the building but not all its rooms.** They have been granted
individual rooms, not the building. Either grant the building or add the rooms.

**Someone cannot find a screen they could see yesterday.** Either it was moved
to a room outside their groups, or a building they were granted was renamed
upstream (see above).

**Someone cannot save a screen: the Room field is required.** They are limited
to location groups, and a screen with no room would disappear from their list.
Pick the room it is in; if it is not in a catalogued room, a user with **All
locations** has to save it.
