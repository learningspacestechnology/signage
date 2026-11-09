# Uploading many files at once

**Bulk Upload Content** creates one piece of content per file you select, and
optionally drops the whole batch into playlists. It's the fastest way to load a
set of posters or a folder of clips.

For a single item, a website, or when you need a custom name, use
[Adding and managing content](help:content) instead.

## Uploading a batch

1. Choose **Bulk Upload Content** from the sidebar, or the button on the
   dashboard.
2. Choose the **Type**: **Image** or **Video**. All files in one batch must be
   the same type.
3. Optionally set **Valid from** and **Expires at**. They apply to every file
   in the batch.
4. Tick any **Playlists** the whole batch should be added to.
5. Click the file picker and select as many files as you like.
6. Save.

![The bulk upload form](screenshot:bulk-upload)

Each file becomes a separate piece of content, **named after the file**. So
`open-day-poster.png` arrives as content called `open-day-poster.png`. Every
item goes into the team you're working in, just as a single upload does — see
[Teams and what you can see](help:teams).

## What to know before you start

**One type per batch.** Images and videos can't be mixed in a single upload. Do
two batches. Websites can't be bulk-uploaded at all, because there is no file to
upload; add those one at a time from **Content**.

**Every file is checked before anything is saved.** The rules are the same as
for single uploads: videos must be `.mp4`, and images must be no larger than
{{ config.MAX_IMG_WIDTH }} × {{ config.MAX_IMG_HEIGHT }}. If **any** file breaks
a rule, **nothing** in the batch is uploaded — see
[If the upload is refused](#if-the-upload-is-refused) below.

**Names come from filenames.** It's worth naming your files sensibly *before*
uploading — `week-1-welcome.png` is much easier to work with later than
`IMG_4471.png`. You can rename items afterwards, but that's one edit per item.

**Everything lands at the end of the playlist.** All items in the batch are added
with the same position, so their order among themselves isn't guaranteed. If
order matters, set it afterwards — see
[Building playlists](help:playlists).

**Dates are shared by the whole batch.** Whatever you put in **Valid from** and
**Expires at** is given to every file. For different dates per item, leave them
blank here and set them on each item afterwards.

## If the upload is refused

The form comes back with one line under **Files** for each file that broke a
rule, starting with that file's name. Nothing from the batch has been saved.

| Message | What it means |
|---|---|
| `poster.png: Image resolution must be at most {{ config.MAX_IMG_WIDTH }}x{{ config.MAX_IMG_HEIGHT }}` | The image is too large. Resize it. |
| `clip.mov: Video files must have .mp4 extensions` | Only `.mp4` videos play. Convert it, or if it's an image, upload it in an Image batch. |
| `notes.pdf: Error opening image file: …` | The file isn't an image the system can read. If it's a video, upload it in a Video batch. |

Fix or remove the files named, then **select the batch again** before saving.
The browser forgets the selected files whenever the form comes back.

## After uploading

Go to **Content** to see the new items. From there you can:

- rename anything whose filename wasn't a good label;
- change **Valid from** / **Expires at** on individual items;
- open the playlist and drag the new entries into the order you want.
