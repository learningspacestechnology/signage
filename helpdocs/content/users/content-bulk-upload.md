# Uploading many files at once

**Bulk Upload Content** creates one piece of content per file you select, and
optionally drops the whole batch into playlists. It's the fastest way to load a
set of posters or a folder of clips.

For a single item, or when you need to set dates or a custom name, use
[Adding and managing content](help:content) instead.

## Uploading a batch

1. Choose **Bulk Upload Content** from the sidebar, or the button on the
   dashboard.
2. Choose the **Type** — all files in one batch must be the same type.
3. Click the file picker and select as many files as you like.
4. Tick any **Playlists** the whole batch should be added to.
5. Save.

![The bulk upload form](screenshot:bulk-upload)

Each file becomes a separate piece of content, **named after the file**. So
`open-day-poster.png` arrives as content called `open-day-poster.png`.

## What to know before you start

**One type per batch.** Images and videos can't be mixed in a single upload. Do
two batches.

**Names come from filenames.** It's worth naming your files sensibly *before*
uploading — `week-1-welcome.png` is much easier to work with later than
`IMG_4471.png`. You can rename items afterwards, but that's one edit per item.

**The same rules apply as for single uploads.** Videos must be `.mp4`, images
must be no larger than
{{ config.MAX_IMG_WIDTH }} × {{ config.MAX_IMG_HEIGHT }}.

**Everything lands at the end of the playlist.** All items in the batch are added
with the same position, so their order among themselves isn't guaranteed. If
order matters, set it afterwards — see
[Building playlists](help:playlists).

**No dates are set.** Bulk-uploaded content has no start or end date. If the
batch is time-limited, open the items afterwards and set **Expires at**.

## After uploading

Go to **Content** to see the new items. From there you can:

- rename anything whose filename wasn't a good label;
- set **Valid from** / **Expires at** dates;
- open the playlist and drag the new entries into the order you want.
