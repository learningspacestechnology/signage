# Adding a scrolling message

A **ticker tape** is a scrolling line of text along the bottom of a screen —
useful for alerts, opening hours, or a standing message that shouldn't take up a
whole slide.

It's set per screen, so the same playlist can carry a message on one display and
not on another.

## Where to find it

Open the screen under **Screens** and expand the **Ticker tape** section.

![The ticker tape settings on a screen](screenshot:ticker-fieldset)

!!! note "You may see fewer settings than are described here"
    Which fields you see depends on your permissions. Turning the ticker on and
    choosing its layout is restricted to administrators; writing the message and
    styling it is available to anyone granted that permission. If you see no
    ticker settings at all, ask an administrator for access.

## Turning it on

1. Tick **Ticker enabled**.
2. Choose a **Ticker layout**:
    - **Overlay** — the ticker is drawn on top of the content, covering the
      bottom strip. Nothing is resized, but the bottom of your content is hidden.
    - **Shrink** — the content is scaled down slightly to make room, so nothing
      is covered.
3. Enter the **Ticker text**.
4. Save.

An empty message means no ticker is shown, even with the ticker enabled. To
switch it off temporarily, clearing the text is enough.

## Choosing a look

Pick a **Ticker style preset**:

| Preset | Looks like |
|---|---|
| **Classic news ticker** | Large white text on solid black, moderate speed |
| **Minimal subtle bar** | Smaller text on a dark, semi-transparent bar |
| **Bold marquee** | Very large text, faster scroll, solid background |

The preset sets everything at once. If it's nearly right, override just the parts
you want:

- **Font size** in pixels.
- **Font colour** and **Background colour**, as colour values like `#ffffff`.
- **Background opacity**, 0–100. Lower values let content show through — the text
  itself always stays fully solid so it remains readable.
- **Scroll speed** in pixels per second. Higher is faster.

Leave any override blank to keep the preset's value for that one thing.

## Writing a good message

- **Keep it short.** The message scrolls past once and comes round again. A
  sentence works; a paragraph doesn't.
- **Front-load the important part.** Someone glancing at the screen sees the
  start of the message, not the end.
- **Check the speed.** Fast enough to come round often, slow enough to read.
  Preview it before leaving.

## Checking it

Use **Preview** on the screen form, or **View on site**, to see the ticker
running over the real content. Adjust the speed and size there rather than
guessing.

## Turning it off

Clear the **Ticker text**, or untick **Ticker enabled** if you have that option.
Either stops the ticker; clearing the text keeps your styling for next time.
