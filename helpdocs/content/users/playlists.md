# Building playlists

A **playlist** is an ordered list of content with a display time for each item.
It's what actually plays on a screen: item 1, item 2, item 3, back to the start.

## Creating a playlist

1. Go to **Playlists** and choose **Add playlist**.
2. Give it a **Name** — this is what you'll pick from when building a schedule,
   so make it descriptive (*Foyer Rotation*, not *Playlist 2*).
3. Optionally add a **Description**.
4. Set the **Default duration** — how many seconds each item shows for, unless
   that item overrides it. 10 seconds is the starting value.
5. Save. You can now add entries.

## Adding and ordering content

Entries are managed on the playlist's own page.

1. Open the playlist.
2. In the entries table, pick a piece of **Content** for each row.
3. Optionally set a **Duration** for that row, in seconds. Leave it blank to use
   the playlist's default duration.
4. Use the handle at the left of each row to **drag entries into the order you
   want**.
5. Save.

![A playlist with its entries](screenshot:playlist-entries)

Each row shows a thumbnail, so you can check you've picked the right item without
opening it.

To remove an entry, tick its **Delete** box and save. That only removes it from
this playlist — the content itself is untouched and stays available to other
playlists.

## How long things show for

- Each entry can set its **own duration**.
- Entries that don't get the playlist's **default duration**.
- **Videos ignore both** and always play to the end.

!!! note "A playlist with exactly one item"
    If a playlist ends up with only one item, that item is held on screen for an
    hour rather than being reloaded every few seconds. This avoids a single image
    flickering as it's replaced by itself.

## Interspersed content

**Interspersed Content** is a single item shown *between* every regular entry —
typically a logo or a standing message.

With entries A, B, C and a logo set as interspersed content, the screen shows:

```
A → logo → B → logo → C → logo → A → …
```

Set it on the playlist form. Leave it blank for a normal rotation. The
interspersed item doesn't need to be one of the playlist's entries, and if it is,
it won't also play in the normal rotation.

!!! tip
    A screen can have its own interspersed content too, set on the screen rather
    than the playlist. Use the playlist for something tied to the content, and
    the screen for something tied to the location.

## Previewing a playlist

Open the playlist and use **View on site**. This plays the playlist in your
browser exactly as a screen would show it — the quickest way to check ordering
and timings before anyone sees it.

## Sharing content between playlists

If several playlists need to include the same announcements, don't copy the
entries. Use inheritance instead, so you maintain the shared items once.

→ [Sharing content between playlists](help:playlist-inheritance)

{% if perms.screens.delete_playlist %}
## Deleting a playlist

From the **Playlists** list, tick it, choose **Delete selected playlists**, and
confirm. As with content, there's no delete button on the edit form itself.

You can't delete a playlist that a schedule is using as its default playlist —
point the schedule at something else first. Deleting a playlist never deletes the
content inside it.
{% endif %}
