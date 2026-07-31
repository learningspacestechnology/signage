# Sharing content between playlists

A playlist can **inherit** from one or more other playlists. Everything in the
parent is played by the child too, without being copied.

This is how you maintain shared announcements once instead of once per screen.

## When to use it

A typical setup:

- **All Buildings** — messages that must appear everywhere.
- **Library** and **Science Wing** — each inherits from *All Buildings*, and adds
  its own local content.

Add a campus-wide notice to *All Buildings* and it appears on both. Remove it
from there and it disappears from both.

## Setting up inheritance

1. Open the **child** playlist — the one that should receive the shared content.
2. Find the **Playlists to inherit from** section.
3. Add a row and pick the **parent** playlist.
4. Save.

You always configure this from the child, choosing its parents.

## What order things play in

The child's **own entries play first**, then the inherited content follows.

So *Library* with two of its own posters, inheriting from *All Buildings* with
three notices, plays: the two Library posters, then the three notices, then round
again.

Inheritance is followed all the way down — a parent that itself inherits from
another playlist brings that content along too.

## Reading the Playlist Tree

**Playlist Tree** in the sidebar draws the relationships between all your
playlists as a diagram. It's the fastest way to answer "what will actually be on
this screen?"

![The playlist inheritance tree](screenshot:playlist-tree)

- **Drag** a circle to pull the layout apart when things overlap.
- **Scroll** to zoom in and out.
- **Hover** a circle for the playlist's name, description and how much content it
  holds.
- **Click** a circle to open that playlist for editing.

## Two rules you'll run into

### Loops aren't allowed

A playlist can't inherit from itself, directly or through a chain — otherwise
playback would never end. The system prevents this rather than warning you about
it: when you're choosing playlists, any that would create a loop is **greyed out
and can't be picked**.

If a playlist you expected is unavailable, follow the chain in the Playlist Tree
and you'll find it already leads back to the one you're editing.

### Both playlists must be yours

To link a child to a parent, you must belong to a team that owns the child **and**
a team that owns the parent.

If you're in teams A and B, you can have a team A playlist inherit from a team B
one. If a colleague's playlist is in a team you're not in, you can't inherit from
it — ask an administrator, who can link across any teams.

## Removing inheritance

Open the child playlist, tick **Delete** on the parent row, and save. The parent
playlist itself is untouched; the child simply stops including its content.
