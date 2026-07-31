# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Dependencies are managed with **uv**, so all `manage.py` commands must be run through `uv run` (e.g. `uv run python manage.py ...`) to use the project's `.venv`. A bare `python manage.py` may target the wrong environment.

```bash
# Run development server
uv run python manage.py runserver

# Run all tests
uv run python manage.py test

# Run tests for a specific app
uv run python manage.py test screens
uv run python manage.py test room_schedules
uv run python manage.py test helpdocs
uv run python manage.py test advertising

# Run a single test. Tests live in `<app>/tests/`, so the module path includes
# the file: there is no `<app>.tests.SomeTests` shortcut.
uv run python manage.py test screens.tests.test_team_scoping.TeamScopingTests
uv run python manage.py test helpdocs.tests.test_help_views.PagePermissionTests.test_page_opens_with_the_permission

# Migrations
uv run python manage.py makemigrations
uv run python manage.py migrate

# Celery worker (requires Redis)
uv run celery -A advertising worker
uv run celery -A advertising beat
```

To add packages: `uv add <package>`.

## Architecture

This is a **Django 4.2** digital signage management system. There are three Django apps:

- **screens/**: Core app managing the display pipeline — Screens, Playlists, Sources, and Schedules.
- **room_schedules/**: Git submodule providing room booking and event integration with Microsoft O365 calendars. The tracked URL in `.gitmodules` is `https://github.com/learningspacestechnology/django_room_schedules.git` (branch `master`) — that is what a fresh clone gets. A working checkout typically also has the maintainer's fork as `origin` and `saty9/django_room_schedules` as `upstream`; check `git -C room_schedules remote -v` before assuming where a change should be pushed. An Artifax integration was removed in migration `0010_remove_artifax` and no Artifax code remains anywhere.
- **helpdocs/**: In-app user documentation rendered from markdown at `/admin/help/`. See [Help documentation](#help-documentation).

### Display Pipeline

```
Screen → Schedule → ScheduleRule → Playlist → PlaylistEntry → Source (image/video/iframe)
```

- A **Screen** (physical display) points to a **Schedule**, which picks the active **Playlist** based on time-of-day rules (**ScheduleRule** with recurrence).
- **Playlists** support inheritance via `PlaylistRelation` (M2M self-reference): child playlists can inherit `Source` items from parent playlists.
- Both **Screen** and **Playlist** have an optional `interspersed_source` that is shown between regular entries.
- **Sources** have `valid_from` / `expires_at` fields; `screens.tasks` runs periodic Celery tasks every 5 minutes to clean up expired sources and update playlists.

### Settings

- `advertising/base_settings.py` — shared base config. **Holds plain default values only — no `os.environ.get`.** This is the single source of defaults; do not add env reads here.
- `advertising/settings.py` — development settings; `from .base_settings import *` then hardcodes local dev overrides (e.g. `ADMIN_SITE_NAME`, O365 credentials). This is where you change values when testing locally — dev is **not** env-driven. **Not tracked in git** — see below.
- `advertising/settings.sample.py` — the committed template for the above.

**First run in a new checkout:**

```bash
cp advertising/settings.sample.py advertising/settings.py
```

The template's defaults are enough to start the app. `manage.py` exits with this
instruction if the file is missing, rather than a bare `ModuleNotFoundError`.

**Three-layer settings model — important.** The same `base_settings.py` is imported by two different override modules depending on environment:

1. `base_settings.py` → plain defaults.
2. **Dev:** `advertising/settings.py` (this repo) overrides with hardcoded values. `DJANGO_SETTINGS_MODULE=advertising.settings`.
3. **Production:** the deploy repo at `/home/vscode/signage_deploy` (separate git repo; this app is its `advertising/` submodule from `learningspacestechnology/signage.git`) ships `docker/advertising/settings.py`, which the Dockerfile copies over the submodule's `settings.py`. It does `from .base_settings import *` then reads `.env` via `os.getenv(...)`. docker-compose loads `.env` through `env_file:`, so `.env` keys become container env vars that those `os.getenv` calls read. Document new overridable keys in `signage_deploy/.env.sample`.

Consequences to remember:
- To make a setting **env-overridable in prod**, add the `os.getenv(...)` read to `docker/advertising/settings.py` (and a line to `.env.sample`) — *not* to `base_settings.py`. A `.env` key with no matching `os.getenv` is inert.
- `os.getenv("KEY", default)` falls back to `default` when KEY is absent; **but an empty `.env` line (`KEY=`) yields `""`, not the default** — fine for strings/bools, but crashes `int(os.getenv(...))` settings.
- A bare `os.getenv("KEY")` (no default) returns `None` when absent — currently `SECRET_KEY` and `HOSTNAME` behave this way (missing `SECRET_KEY` fails startup; missing `HOSTNAME` leaves `ALLOWED_HOSTS=[None, '127.0.0.1']`).
- After bumping `base_settings.py`, the deploy submodule pointer must be advanced to a commit containing the change before the deploy override can rely on it.

Key env-driven settings (read in the deploy `settings.py`): `O365_CLIENT_ID`, `O365_TENANT_ID`, `O365_CLIENT_SECRET`, `AUTO_MAKE_SCREENS_FOR_NEW_IPS`, `ADMIN_SITE_NAME`, `ENTRA_*`, `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`.

**`advertising/settings.py` is untracked and ignored.** It routinely holds real credentials, so only `advertising/settings.sample.py` is committed. Consequences:

- Changing a local value never shows up in `git status` and can never be committed by accident.
- **Adding a new setting means updating three places**, none of which the others will remind you about: `base_settings.py` for the default, `settings.sample.py` so the next person knows it exists, and the deploy repo's `docker/advertising/settings.py` + `.env.sample` if it should be env-overridable in production.
- A fresh clone has no `settings.py` at all. `manage.py` catches that and prints the `cp` command.
- The Docker image is unaffected: its Dockerfile does `ADD docker/advertising/settings.py advertising/.`, creating the file at build time.

Celery broker/backend defaults to `redis://redis:6379/0`.

**`ADMIN_SITE_NAME`** drives the admin name on the login page ("Welcome back to …"), the top-left header on every page, and the logout page. `UNFOLD["SITE_TITLE"]`/`["SITE_HEADER"]` point at the callable `"advertising.admin.site_name"` (resolved lazily at render time), so overriding `ADMIN_SITE_NAME` in any layer takes effect with no need to rebuild the `UNFOLD` dict.

### Access control

`advertising/middleware.py` (`IpAccessControlMiddleware`) gates every URL outside `/admin/` and `/static/`. A request is allowed if the user is an authenticated admin (`is_staff`), or if its client IP is registered as a `Screen.ip` or as a `room_schedules.IpAddress` (room/building/group). Denied HTML GETs are redirected to `/admin/login/`; everything else gets `403`. The screen-discovery endpoints (`/screen/`, `/api/screen/`, `/meta`, `/api/meta`, `/api/unconfigured`) and the room-schedule entry point (`/event_schedules/`) are always allowed through regardless of IP, because their views handle unregistered IPs themselves — either auto-creating a `Screen` (when `AUTO_MAKE_SCREENS_FOR_NEW_IPS=True`) or rendering the unconfigured-screen page/JSON so the operator can read off the device's IP. Sub-paths with explicit IDs (`/api/screen/<id>`, `/api/meta/<id>`, `/playlist/<id>`, `/event_schedules/<venue_id>…`) remain gated. Toggle with `IP_ACCESS_CONTROL_ENABLED` (default `True`); when `DEBUG=True`, requests from `127.0.0.1`/`::1` bypass the gate so local dev just works.

**Media is gated in production too.** `/media/<path>` is not served statically — it routes to `advertising.views.serve_media`, which rejects paths escaping `MEDIA_ROOT` and then hands off with `X-Accel-Redirect: /protected-media/<path>`. In the deploy stack nginx proxies `/media/` to the app and declares `/protected-media/` as `internal`, so the bytes are only reachable through a request Django has already authorised. Do not add a direct nginx `location /media/` that serves from disk — that bypasses the gate entirely.

**Behind a reverse proxy:** the IP comes from `request.META['REMOTE_ADDR']` by default, which will be the proxy's loopback address — every request would look the same and the gate would deny everyone. Set `USE_FIRST_FORWARDED_FOR_IP=True` (leftmost `X-Forwarded-For` entry, i.e. original client) or `USE_LAST_FORWARDED_FOR_IP=True` (rightmost, i.e. nearest trusted hop) in production settings, and make sure nginx forwards `X-Forwarded-For`. Pick `_FIRST_` only if the whole proxy chain is trusted, since clients can spoof leading XFF entries otherwise.

### Teams (multi-tenancy) vs. Groups (capabilities)

The admin uses two orthogonal authorisation layers — keep them separate.

- **`Team`** (in `screens.models.team`) scopes *what you can see*. Each `Source`, `Playlist`, `Screen`, and `Schedule` carries a `teams` M2M; staff users see only objects whose `teams` overlap with their own membership. Active team is held in `request.session['active_team_id']` and resolved to `request.active_team` by `ActiveTeamMiddleware`. Superusers default to the `ALL_TEAMS` sentinel (see all teams' content). Regular users default to their first team alphabetically. Switching goes through `admin:set_active_team`; the picker itself is this project's override of `templates/unfold/helpers/userlinks.html` plus `screens/templatetags/team_switcher.py` — **not** Unfold's `SITE_DROPDOWN`, which is not configured.
- **`auth.Group`** + Django `Permission` scope *what you can do* (add/change/delete on each model). Groups are unchanged from stock Django — create `Content Editor`, `Scheduler`, etc. with the relevant model permissions.
- Both layers compose: the queryset is intersected with the team filter, then the standard permission gates apply.
- Only superusers can edit the `teams` field on an object or manage `Team` / `TeamMembership` records. Regular users have `teams` hidden in the admin and inherit their currently active team automatically on create.
- Cross-team `PlaylistRelation` inheritance: a regular user may wire `child → parent` if they are a member of at least one team owning each (so a user in teams A+B can have a Team A playlist inherit from a Team B playlist). Superusers can wire any relation.
- A team can only be deleted when it has zero members and zero owned objects. Enforced both in `TeamAdmin.has_delete_permission` and a `pre_delete` signal on `Team`.

### Admin UI

Uses **django-unfold** for styling.

- `advertising/base_settings.py` holds the `UNFOLD` dict: sidebar navigation (each item with its own `permission` lambda), the dashboard callback, and the environment label.
- `advertising/admin.py` carries the cross-cutting customisation: `dashboard_callback`, the team switcher, `set_active_team_view`, and a monkey-patch of `admin.site.get_urls` that injects the help, O365 and set-active-team URLs. It also unregisters and re-registers `User`, `Group` and the celery-beat/results models so they pick up Unfold styling — **so anything that walks `admin.site` must run after this module is imported**, which is why `attach_help_links()` is its last statement.
- Screen/Source/Playlist/Schedule/Team admin logic lives in `screens/admin.py`; Building/Room/RoomGroup and the custom O365 pages in `room_schedules/admin.py`.

### Help documentation

User-facing documentation lives in `helpdocs/content/{users,technical}/` as markdown and is rendered at `/admin/help/`. Deployment is deliberately not covered — that belongs to the deploy repo.

Visibility is gated at three levels, each narrowing the one above:

1. **Audience** — `AUDIENCE_PERMISSIONS` in `helpdocs/registry.py`. The `users` set needs only staff access; the `technical` set needs `helpdocs.view_technical_docs`, granted via a Group (it is a *capability*, not a tenancy concern).
2. **Page** — `Page.permissions` in the registry, holding *any* of them by default (`require_all=True` to require all). These mirror the sidebar's own permission lambdas, so a page about a screen the reader cannot open never appears. A gated page is dropped from the index, skipped by prev/next, hidden from the contextual "?" link, and returns 403 if fetched directly. A section left with no visible pages disappears entirely.
3. **Section within a page** — wrap it in `{% if perms.app_label.codename %}…{% endif %}`. Markdown is rendered through the Django template engine, so `perms` is just available; there is no custom syntax.

Rendered output is cached per (file mtime, permissions-the-page-branches-on), so gating a section does not leak one reader's version to another. Only the permissions a page actually references enter the key, so a page branching on one permission has two cache variants, not one per user.

Two cautions: a mistyped permission is silent at runtime — it evaluates false and the content simply vanishes, which is why `check_help_docs` validates every name against the permission table. And hiding a section can strand references to it, so gate whole self-contained sections rather than sentences.

**Help documentation is part of the definition of done.** Any change that adds, alters or removes user-facing behaviour — a model field users set, a form, an admin action, a view, a sidebar entry, a validation rule, a permission — must update the matching page under `helpdocs/content/` **in the same change**. A new feature gets a new page (plus an entry in `helpdocs/registry.py`) or a new section on the closest existing page.

Conventions when writing a page:

- **Never hardcode a configurable value.** Write `{{ config.NAME }}` and add the key to `CONFIG_KEYS` in `helpdocs/rendering.py`. `ADMIN_SITE_NAME` and `MAX_IMG_WIDTH`/`MAX_IMG_HEIGHT` already differ between base and dev, so a literal would be wrong somewhere.
- **Link between pages with `[text](help:slug)`** (or `help:audience/slug` to cross audiences). Plain relative links break: page URLs end in a slash, so `](dashboard)` resolves *below* the current page.
- **Reference screenshots as `![Alt](screenshot:name)`**, with a matching `Shot` in `helpdocs/screenshots.py`. An uncaptured screenshot renders as a labelled placeholder, so every page must read correctly without its images.
- Page titles come from the first `#` heading, not from the registry.
- Markdown is rendered through the Django template engine first, so a page that needs to *show* template syntax must wrap it in `{% verbatim %}`.

Two commands:

```bash
# Validate: manifest vs disk, config keys, screenshot specs, help: links,
# and which admin changelists have no page. Run before finishing.
uv run python manage.py check_help_docs

# Re-capture screenshots (Playwright + a throwaway seeded database).
DJANGO_SETTINGS_MODULE=advertising.screenshot_settings \
    uv run python manage.py capture_help_screenshots [--only NAME]
```

`capture_help_screenshots` must be run with `advertising.screenshot_settings` — it drops and rebuilds the database it points at, and that settings module substitutes placeholder Microsoft credentials so no capture can touch the live tenant. It only rewrites a PNG that has materially changed, so re-running it doesn't churn the repo.

### Models location

All `screens` models are split into individual files under `screens/models/` and re-exported from `screens/models/__init__.py`. The `room_schedules` models follow the same pattern under `room_schedules/models/`.

`helpdocs` is the exception: a single `models.py` holding one unmanaged model that exists only to carry the `view_technical_docs` permission. It has no table and no rows.
