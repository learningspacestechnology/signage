# Adding and managing content

**Content** is a single thing that can be displayed: an image, a video, or a live
web page. Content is never shown on its own — it has to be added to a playlist
before anything happens.

{% if perms.screens.add_source %}
To upload many files in one go, see
[Uploading many files at once](help:content-bulk-upload).
{% endif %}

## The three types

| Type | What it is | What you provide |
|---|---|---|
| **Image** | A still picture | An image file |
| **Video** | A video clip | An `.mp4` file |
| **Website** | A live web page embedded in the screen | A web address |

The form changes as you pick a type: choose Image or Video and the file picker is
enabled; choose Website and you enter an address instead. You never fill in both.

## Adding one item

1. Go to **Content** in the sidebar and choose **Add content**.
2. Pick the **Type**.
3. Give it a **Name**. This is only ever seen by you and your colleagues, in
   lists and when picking content for a playlist — make it something you'll
   recognise later, like *Open Day poster – June*.
4. Upload the **File**, or enter the **Website Address**.
5. Optionally set **Valid from** and **Expires at** — see
   [Timing content](#timing-content).
6. Optionally tick the **Playlists** it should be added to. This saves going to
   each playlist separately.
7. Save.

![Adding a piece of content](screenshot:content-add)

!!! note "Some playlists may be greyed out"
    A playlist is disabled in that list when adding your content to it would
    create a loop — see
    [Sharing content between playlists](help:playlist-inheritance).

## Timing content

Two optional fields control when a piece of content is eligible to play:

- **Valid from** — nothing shows before this moment. Leave blank to start
  immediately.
- **Expires at** — nothing shows after this moment. Leave blank to run forever.

This is the tidiest way to handle anything with a date attached. Upload next
month's poster now, set **Valid from** to the first of the month, and it appears
on its own.

!!! warning "Expired content is deleted, not just hidden"
    Once **Expires at** has passed, the item stops playing, and a background job
    then removes it and its file permanently. If you want to reuse something next
    year, download a copy first, or clear the expiry date before it passes.

## What the rules are

If a file is rejected, it will be one of these:

- **Videos must be `.mp4`.** Other video formats aren't accepted. Convert it
  first.
- **Images must be no larger than {{ config.MAX_IMG_WIDTH }} × {{ config.MAX_IMG_HEIGHT }}.**
  Resize a larger image before uploading.
- **Images and videos must have a file.** A name and type alone isn't enough.
  Websites need an address instead.
- **Everything must belong to a team.** This is filled in for you, so you'll only
  see this if something has gone unusual.

## Finding content later

On the **Content** list you can:

- **Search** by name.
- **Filter by playlist**, to see everything currently in one playlist.
- **Filter by type**, to see just images, videos or websites.
- **Browse by date** using the year/month links along the top, which work on the
  date the item was uploaded.

The list also shows a thumbnail, the resolution, who uploaded it, and which
playlists it's in.

![The content list](screenshot:content-list)

## Editing and previewing

Click an item's **name** — the underlined text in the Name column — to open it.
The form shows a **Preview** so you can confirm you're editing what you think you
are.

Changing the file, the type, the web address or the timing dates causes every
playlist containing that item to refresh, so screens pick the change up within
about a minute. Renaming it does not — the name is only ever seen by you.

{% if perms.screens.delete_source %}
## Deleting content

Deleting removes the item from every playlist that uses it.

From the **Content** list, tick the items, choose **Delete selected content**
from the action menu, and confirm.

!!! note
    There is no delete button on the edit form itself. This is deliberate — it
    makes it much harder to delete something while you meant to change it.
{% endif %}
