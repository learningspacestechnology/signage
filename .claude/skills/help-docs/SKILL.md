---
name: help-docs
description: Audit, write or update the in-app help documentation under helpdocs/content/, and re-capture its screenshots. Use when adding or changing a user-facing feature, when asked to check whether the docs are current, or when the user says "update the help docs".
---

# Help documentation

The in-app documentation at `/admin/help/`, rendered from markdown in
`helpdocs/content/`. This skill keeps it honest.

## Two audiences

| Set | Directory | Who reads it | Gate |
|---|---|---|---|
| Users | `helpdocs/content/users/` | Everyday operators | Staff access only |
| Technical | `helpdocs/content/technical/` | People administering the system | `helpdocs.view_technical_docs` |

**Deployment is out of scope** for both. Docker, `.env`, TLS and upgrades belong
to the deploy repo. When a fix needs a configuration change, say so and say what
to ask for — don't explain how to make it.

## Three levels of visibility

Each narrows the one above:

1. **Audience** — `AUDIENCE_PERMISSIONS` in `helpdocs/registry.py`.
2. **Page** — `Page.permissions`, a tuple of `'app_label.codename'`. Holding
   *any* is enough unless `require_all=True`. Mirror the sidebar's own
   permission lambda for the screen the page documents; that keeps the docs and
   the navigation telling the same story. A gated page vanishes from the index,
   is skipped by prev/next, is hidden from the contextual "?", and 403s if
   fetched directly.
3. **Section** — `{% if perms.app_label.codename %}…{% endif %}` around it.
   Markdown goes through the Django template engine, so `perms` is simply
   available.

Judgement, not mechanics:

- **Gate a page** when the reader cannot reach the screen it describes at all.
- **Gate a section** when one action within a page is restricted — deleting,
  bulk uploading, ticker layout.
- **Gate nothing** on concept and troubleshooting pages. Someone diagnosing a
  problem needs the whole picture, including the parts they'd have to ask a
  colleague to do.
- Gate **whole self-contained sections**, never a sentence. Hiding a sentence
  strands the references around it.
- A mistyped permission is **silent at runtime** — it evaluates false and the
  content disappears with no error. `check_help_docs` validates every name
  against the permission table; never skip it after touching a permission.

Rendered output is cached per (mtime, the permissions that page branches on), so
a gated section can't leak between readers. Nothing to do — but if you add
permission logic outside a page's own markup, that invariant is yours to keep.

## Always start here

```bash
uv run python manage.py check_help_docs
```

It reports, as **errors**: a registry entry with no file (or a file with no
registry entry), a missing `# ` heading, a `config.X` that isn't whitelisted, a
`screenshot:` reference with no spec, a broken `help:` link, and any page that
fails to render. As **warnings**: uncaptured screenshots, unused specs, and admin
changelists with no help page mapped.

Fix every error. Warnings are judgement calls — an unmapped admin either needs a
page or an entry in `COVERAGE_EXEMPT` with a reason.

## Auditing after a change

1. Run `check_help_docs`.
2. Look at what actually changed:
   ```bash
   git diff --stat HEAD~1 -- screens/ room_schedules/ advertising/ templates/
   ```
   Anything touching a model field users set, a form, an admin action, a view, a
   sidebar entry, a validation rule or a permission needs a documentation change
   too.
3. Check whether the matching page under `helpdocs/content/` was touched in the
   same change. If not, that's the gap.
4. Report gaps concretely — name the file and the section, not "the docs may need
   updating".

## Writing a page

Structure that the existing pages follow, and new ones should:

- One `# Title` (this *is* the page title — the registry doesn't hold it).
- A one- or two-sentence statement of what the page is for, and a pointer to the
  adjacent page if the reader is in the wrong place.
- Concept first, then numbered steps. Steps should be followable while looking at
  the screen being described.
- End with the failure modes: what the error messages mean, and what to do.

Voice: direct, second person, no marketing. Say what a thing does and what it
costs. Prefer "lowest priority number wins" over "priority determines
precedence". Where behaviour is surprising — expired content being *deleted*
rather than hidden, moving a room silently dropping it from a group — call it out
in an `!!! warning` block rather than burying it.

### Mechanics that will bite you

- **Never hardcode a configurable value.** Write `{{ config.NAME }}` and add the
  key to `CONFIG_KEYS` in `helpdocs/rendering.py`. `ADMIN_SITE_NAME` and
  `MAX_IMG_*` already differ between base and dev.
- **Link with `[text](help:slug)`**, or `help:audience/slug` across audiences.
  Relative links break — page URLs end in a slash.
- **Screenshots are `![Alt](screenshot:name)`** with a matching `Shot` in
  `helpdocs/screenshots.py`. Uncaptured ones render as a labelled placeholder, so
  **every page must read correctly with no images at all**. Never make a
  screenshot load-bearing.
- Markdown goes through the Django template engine first, so literal template
  syntax needs `{% verbatim %}`.
- Admonitions are `!!! note`, `!!! tip`, `!!! warning`, `!!! danger`.

### Adding a page

1. Write `helpdocs/content/<audience>/<slug>.md`.
2. Add a `Page(...)` to `PAGES` in `helpdocs/registry.py`, in the right
   `section`. Sections are ordered by `SECTION_ORDER`.
3. Set `admin_url_names` to the admin views the page documents — that's what puts
   the contextual "?" link above those changelists and forms.
4. Set `permissions` to match the sidebar entry for those same screens, unless
   the page is conceptual.
5. Re-run `check_help_docs`.

## Screenshots

```bash
DJANGO_SETTINGS_MODULE=advertising.screenshot_settings \
    uv run python manage.py capture_help_screenshots [--only NAME] [--list]
```

Only re-capture what the change affects; `--only` takes the shot name and is
repeatable. A full run rebuilds the throwaway database and takes a couple of
minutes.

- It **must** run with `advertising.screenshot_settings`. That module points at a
  throwaway database under `.help-capture/` and substitutes placeholder Microsoft
  credentials — the dev settings hold real ones and run tasks eagerly. The
  command refuses to start otherwise.
- Demo data is invented (`helpdocs/demo_data.py`) so no real username, room or
  mailbox is ever committed. Keep it that way.
- A PNG is only rewritten when it differs materially, so pages carrying a clock
  don't churn the repo. If a shot you expect to change reports `unchanged`, lower
  `--threshold`.
- After capturing, **look at the images**, don't just trust the exit code. Past
  failures were a collapsed fieldset and a sticky save bar sitting across the
  middle of a crop — both "successful" captures.

## Finishing

```bash
uv run python manage.py check_help_docs
uv run python manage.py test helpdocs
```

Never `git add .` — `advertising/settings.py` is tracked despite being gitignored
and holds real credentials in a working checkout. Stage paths explicitly.
