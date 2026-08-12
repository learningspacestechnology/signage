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
    flickering as it's replaced by itself. The hold doesn't apply when the
    playlist also has interspersed content, because then the item is alternating
    with something rather than replacing itself.

## Interspersed content

An **Interspersed playlist** is mixed in *between* a playlist's own entries —
typically a logo or a standing message. Its items are not part of the normal
rotation.

The **Interspersed rate** decides how often. It's the number of the playlist's
own entries that play before one interspersed item. With entries A, B, C and a
logo playlist at rate 1:

```
A → logo → B → logo → C → logo → A → …
```

At rate 2 the logo appears half as often:

```
A → B → logo → C → A → logo → B → C → …
```

If the interspersed playlist holds more than one item, they take turns — each
insertion point shows the next one, continuing where it left off rather than
restarting.

Set both on the playlist form. Leave the playlist blank for a normal rotation.

!!! note "Timings come from the interspersed playlist"
    Interspersed items use *their own* playlist's durations and default
    duration, not the one they're mixed into. So a logo playlist set to 4
    seconds flashes past between slides that each show for 15.

!!! note "An item can appear in both"
    If a piece of content is both an entry in the playlist and an item in the
    interspersed playlist, it plays in both roles. Content that has expired, or
    whose start date hasn't arrived, is skipped in an interspersed playlist just
    as it is in a normal one.

!!! tip
    A screen can have its own interspersed playlist too, set on the screen
    rather than the playlist. Use the playlist for something tied to the
    content, and the screen for something tied to the location. Where both are
    set, the screen's is mixed into the result of the playlist's — so with a
    logo playlist at rate 1 and a room sign at rate 1, a screen shows
    `A → sign → logo → sign → B → sign → …`.

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
