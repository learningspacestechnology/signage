# Adding a scrolling message

A **ticker tape** is a scrolling line of text along the bottom of a screen —
useful for alerts, opening hours, or a standing message that shouldn't take up a
whole slide.

It's set per screen, so the same playlist can carry a message on one display and
not on another.

## Where to find it

Open the screen under **Screens** and expand the **Ticker tape** section.

![The ticker tape settings on a screen](screenshot:ticker-fieldset)

!!! note "You may see fewer settings than the picture shows"
    The ticker is split across two permissions and the picture shows both. One
    covers turning the ticker on and choosing its layout — the shape of the
    display. The other covers the message itself and how it looks. You may hold
    either or both, so parts of this page may describe fields you cannot see.

{% if perms.screens.change_ticker_settings %}
## Turning it on

1. Tick **Ticker enabled**.
2. Choose a **Ticker layout**:
    - **Overlay** — the ticker is drawn on top of the content, covering the
      bottom strip. Nothing is resized, but the bottom of your content is hidden.
    - **Shrink** — the content is scaled down slightly to make room, so nothing
      is covered.
3. Save.

Enabling the ticker is only half of it — a screen with the ticker on but no
message shows nothing at all.

!!! note "Interspersed content set on the screen"
    A screen with the ticker on can't also mix in its own **Interspersed
    playlist**, so those fields disappear from the screen form while the ticker
    is enabled. Anything already set is kept and applies again as soon as the
    ticker is turned off. A *playlist's* own interspersed content is unaffected
    and plays either way — see
    [Interspersed content](help:playlists).
{% endif %}

{% if perms.screens.change_ticker_text %}
## Writing the message

Enter the **Ticker text** and save.

An empty message means no ticker is shown, even with the ticker enabled. To
switch a message off temporarily, clearing the text is enough.

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
{% endif %}

## Checking it

Use **Preview** on the screen form, or **View on site**, to see the ticker
running over the real content. Judge it there rather than guessing.

## Turning it off

{% if perms.screens.change_ticker_text %}
Clear the **Ticker text**. That stops the ticker while keeping your styling for
next time.
{% endif %}
{% if perms.screens.change_ticker_settings %}
Untick **Ticker enabled** to switch the feature off on that screen entirely.
{% endif %}
