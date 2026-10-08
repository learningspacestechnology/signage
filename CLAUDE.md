# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`KNOWN_ISSUES.md` holds bugs that have been diagnosed but deliberately not fixed yet, each with its cause and intended fix. Check it before investigating odd behaviour, and remove an entry when it is fixed.

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

This is a **Django 4.2** digital signage management system. There are four Django apps:

- **screens/**: Core app managing the display pipeline — Screens, Playlists, Sources, and Schedules.
- **room_schedules/**: Git submodule providing room booking and event integration with Microsoft O365 calendars. The tracked URL in `.gitmodules` is `https://github.com/learningspacestechnology/django_room_schedules.git` (branch `master`) — that is what a fresh clone gets. A working checkout typically also has the maintainer's fork as `origin` and `saty9/django_room_schedules` as `upstream`; check `git -C room_schedules remote -v` before assuming where a change should be pushed. An Artifax integration was removed in migration `0010_remove_artifax` and no Artifax code remains anywhere.
- **estate/**: Read-only mirror of the University's Learning Spaces Datastore (LSD) — `Campus`, `Building`, `Room` — plus the `Screen.room` target, the link models tying `room_schedules` records to it, and `LocationGroup` (location-based access). See [Estate directory](#estate-directory) and [Location groups](#teams-location-groups-and-groups).
- **helpdocs/**: In-app user documentation rendered from markdown at `/admin/help/`. See [Help documentation](#help-documentation).

### Display Pipeline

```
Screen → Schedule → ScheduleRule → Playlist → PlaylistEntry → Source (image/video/iframe)
```

- A **Screen** (physical display) points to a **Schedule**, which picks the active **Playlist** based on time-of-day rules (**ScheduleRule** with recurrence).
- **Playlists** support inheritance via `PlaylistRelation` (M2M self-reference): child playlists can inherit `Source` items from parent playlists.
- Both **Screen** and **Playlist** have an optional `interspersed_playlist` plus an `interspersed_rate`: that playlist's items are mixed in after every `rate` regular items. The player composes them base → playlist-level → screen-level, so the screen's rate counts items that already include the playlist's insertions. Ticker screens cannot play the screen-level stream — see `KNOWN_ISSUES.md`, and `ScreenAdmin` hides the fields while `ticker_enabled` is set.
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

Key env-driven settings (read in the deploy `settings.py`): `O365_CLIENT_ID`, `O365_TENANT_ID`, `O365_CLIENT_SECRET`, `AUTO_MAKE_SCREENS_FOR_NEW_IPS`, `ADMIN_SITE_NAME`, `ENTRA_*`, `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`, `LSD_API_KEY`/`LSD_API_BASE_URL`/`LSD_SYNC_*`.

**`advertising/settings.py` is untracked and ignored.** It routinely holds real credentials, so only `advertising/settings.sample.py` is committed. Consequences:

- Changing a local value never shows up in `git status` and can never be committed by accident.
- **Adding a new setting means updating three places**, none of which the others will remind you about: `base_settings.py` for the default, `settings.sample.py` so the next person knows it exists, and the deploy repo's `docker/advertising/settings.py` + `.env.sample` if it should be env-overridable in production.
- A fresh clone has no `settings.py` at all. `manage.py` catches that and prints the `cp` command.
- The Docker image is unaffected: its Dockerfile does `ADD docker/advertising/settings.py advertising/.`, creating the file at build time.

**Always read settings through `django.conf.settings`, at the moment you need the value.** Two rules, both learned the hard way:

- **Never `from advertising.settings import SOME_KEY`.** That imports the settings *module*, so the name ignores `DJANGO_SETTINGS_MODULE` and is invisible to `override_settings`. It resolves correctly in production only by the accident that the Dockerfile copies the deploy override onto that exact module. It is why `advertising.screenshot_settings` could not isolate `MAX_IMG_*` and one developer's numbers reached the shipped help screenshots, and why an `@override_settings` in `screens/tests/test_playlist_json.py` sat inert for a year. `room_schedules/views.py:37` shows the correct shape.
- **Never let a setting reach a model field definition.** Django records the whole field — `help_text` included, though it never touches the schema — in migration state, and an f-string in a class body is evaluated once at import. A per-deployment value baked in there means whoever ran `makemigrations` wrote their own site's value into shared history, and every other site reports a pending migration forever. `format_lazy` does **not** save you: the autodetector resolves the proxy when comparing and the migration writer forces `Promise` to `str`. Compute the text at request time instead — `screens/models/source.py`'s `file_help_text()`, applied in the form's `__init__`, is the pattern to copy.

`advertising/tests/test_migration_state.py` fails, naming the offending field, if the second rule is broken. Run the suite before assuming a new setting is harmless.

Celery broker/backend defaults to `redis://redis:6379/0`.

**`ADMIN_SITE_NAME`** drives the admin name on the login page ("Welcome back to …"), the top-left header on every page, and the logout page. `UNFOLD["SITE_TITLE"]`/`["SITE_HEADER"]` point at the callable `"advertising.admin.site_name"` (resolved lazily at render time), so overriding `ADMIN_SITE_NAME` in any layer takes effect with no need to rebuild the `UNFOLD` dict.

### Access control

`advertising/middleware.py` (`IpAccessControlMiddleware`) gates every URL outside `/admin/` and `/static/`. A request is allowed if the user is an authenticated admin (`is_staff`), or if its client IP is registered as a `Screen.ip` or as a `room_schedules.IpAddress` (room/building/group). Denied HTML GETs are redirected to `/admin/login/`; everything else gets `403`. The screen-discovery endpoints (`/screen/`, `/api/screen/`, `/meta`, `/api/meta`, `/api/unconfigured`) and the room-schedule entry point (`/event_schedules/`) are always allowed through regardless of IP, because their views handle unregistered IPs themselves — either auto-creating a `Screen` (when `AUTO_MAKE_SCREENS_FOR_NEW_IPS=True`) or rendering the unconfigured-screen page/JSON so the operator can read off the device's IP. Sub-paths with explicit IDs (`/api/screen/<id>`, `/api/meta/<id>`, `/playlist/<id>`, `/event_schedules/<venue_id>…`) remain gated. Toggle with `IP_ACCESS_CONTROL_ENABLED` (default `True`); when `DEBUG=True`, requests from `127.0.0.1`/`::1` bypass the gate so local dev just works.

**Media is gated in production too.** `/media/<path>` is not served statically — it routes to `advertising.views.serve_media`, which rejects paths escaping `MEDIA_ROOT` and then hands off with `X-Accel-Redirect: /protected-media/<path>`. In the deploy stack nginx proxies `/media/` to the app and declares `/protected-media/` as `internal`, so the bytes are only reachable through a request Django has already authorised. Do not add a direct nginx `location /media/` that serves from disk — that bypasses the gate entirely.

**Behind a reverse proxy:** the IP comes from `request.META['REMOTE_ADDR']` by default, which will be the proxy's loopback address — every request would look the same and the gate would deny everyone. Set `USE_FIRST_FORWARDED_FOR_IP=True` (leftmost `X-Forwarded-For` entry, i.e. original client) or `USE_LAST_FORWARDED_FOR_IP=True` (rightmost, i.e. nearest trusted hop) in production settings, and make sure nginx forwards `X-Forwarded-For`. Pick `_FIRST_` only if the whole proxy chain is trusted, since clients can spoof leading XFF entries otherwise.

### Teams, location groups and Groups

The admin uses three orthogonal authorisation layers — keep them separate. Teams decide *whose* objects you see, location groups decide *where* (which estate places, and so which screens), and `auth.Group` permissions decide *what you can do*.

- **`Team`** (in `screens.models.team`) scopes *what you can see*. Each `Source`, `Playlist`, `Screen`, and `Schedule` carries a `teams` M2M; staff users see only objects whose `teams` overlap with their own membership. Active team is held in `request.session['active_team_id']` and resolved to `request.active_team` by `ActiveTeamMiddleware`. Superusers default to the `ALL_TEAMS` sentinel (see all teams' content). Regular users default to their first team alphabetically. Switching goes through `admin:set_active_team`; the picker itself is this project's override of `templates/unfold/helpers/userlinks.html` plus `screens/templatetags/team_switcher.py` — **not** Unfold's `SITE_DROPDOWN`, which is not configured.
- **`auth.Group`** + Django `Permission` scope *what you can do* (add/change/delete on each model). Groups are unchanged from stock Django — create `Content Editor`, `Scheduler`, etc. with the relevant model permissions.
- **`LocationGroup`** (in `estate.models.access`) scopes *where*. A named set of `Campus`/`Building`/`Room` grants with members (through `LocationGroupMembership`); a user's places are the union over their groups, each grant covering everything beneath it, and a room grant revealing its building and campus but not their other rooms. All scoping goes through `estate/location_scope.py`: `scope_to_locations(qs, request)` for Room/Building/Campus/Screen querysets, `scope_screens` for team ∩ location, `sees_all_locations(request)` for the exemption check. Content, playlists and schedules are not location-bound.
- **Location access fails closed.** No group ⇒ no screens and no estate rows. Exempt: superusers and holders of `estate.access_all_locations`, which estate migration `0005` granted — via an "All locations" auth Group — to every staff user who existed then. So **any test that logs in a non-superuser to look at screens or the estate must call `estate.tests.helpers.grant_all_locations(user)`** (or put them in a location group), or it sees nothing. Unlike `scope_to_active_team`, there is no fail-open branch: it depends only on `request.user`, never on middleware having run.
- Location scoping uses `pk__in` subqueries, never joins, on purpose: a join from Campus/Building down to rooms is reused by any later `Count()` on the same path and silently changes what it counts, and `.distinct()` breaks bulk `.delete()`. Keep it that way.
- `ScreenAdmin.formfield_for_foreignkey` sets the `room` field's queryset to the scoped rooms, and `ScreenAdmin.get_form` does the same for `building`. Both are **load-bearing**: the picker's options already come from the scoped `RoomAdmin`, but each field *validates* against its own queryset, which defaults to the whole estate — so without them a crafted POST places a screen anywhere. For restricted users `building` is `required`, and `ScreenAdminForm.clean` refuses a blank room unless the building is held outright (`wholly_visible_buildings`, set per request by `get_form`) — otherwise the screen would vanish from their list on save.
- A screen with no room but a `building` (a foyer — most are not catalogued) is visible to a restricted user only through a **building or campus grant** (`wholly_visible_building_ids`), never through a room grant in that building. A screen *with* a room is scoped by the room alone, so a stale `building` cannot widen access.
- The layers compose: the queryset is intersected with the team filter and, for screens and estate rows, the location filter; then the standard permission gates apply.
- Only superusers can edit the `teams` field on an object or manage `Team` / `TeamMembership` records. Regular users have `teams` hidden in the admin and inherit their currently active team automatically on create.
- Cross-team `PlaylistRelation` inheritance: a regular user may wire `child → parent` if they are a member of at least one team owning each (so a user in teams A+B can have a Team A playlist inherit from a Team B playlist). Superusers can wire any relation.
- A team can only be deleted when it has zero members and zero owned objects. Enforced both in `TeamAdmin.has_delete_permission` and a `pre_delete` signal on `Team`.
- Only superusers can manage location groups or their membership (`LocationGroupAdmin`, the user-page inline, the add-user field), for the same reason as teams: a location group grants access. The **Room Schedules admin is not location-scoped yet** — see `KNOWN_ISSUES.md`.

### Admin UI

Uses **django-unfold** for styling.

- `advertising/base_settings.py` holds the `UNFOLD` dict: sidebar navigation (each item with its own `permission` lambda), the dashboard callback, and the environment label.
- `advertising/admin.py` carries the cross-cutting customisation: `dashboard_callback`, the team switcher, `set_active_team_view`, the accent-colour callables and `set_accent_view`, and a monkey-patch of `admin.site.get_urls` that injects the help, O365, set-active-team and set-accent URLs. It also unregisters and re-registers `User`, `Group` and the celery-beat/results models so they pick up Unfold styling — **so anything that walks `admin.site` must run after this module is imported**, which is why `attach_help_links()` is its last statement.
- Screen/Source/Playlist/Schedule/Team admin logic lives in `screens/admin.py`; Building/Room/RoomGroup and the custom O365 pages in `room_schedules/admin.py`.

#### Accent colours, and what couples us to django-unfold

Each user picks an admin accent colour from the sidebar user menu; the choice is stored on `screens.models.UserPreference` and the palettes live in `screens/accents.py`. The mechanism leans on several **django-unfold internals that are not public API**, and every one of them fails *silently and cosmetically* — a wrong colour, an unreadable link, a vanished picker — with nothing in the deploy erroring. The analysis below was done against **django-unfold 0.82.0** (pinned in `pyproject.toml`); re-check it on every bump.

**Forked vendor templates.** Three Unfold helpers are copied into `templates/unfold/helpers/`, which means Unfold's own changes to them are silently ignored:

| File | Why it is forked |
|---|---|
| `navigation_user.html` | one added `{% include %}` for `accent_switch.html` |
| `userlinks.html` | wraps the environment label in the team picker |
| `unauthenticated_header.html` | drops "Return to site" from the login page |

On an unfold upgrade, **re-copy each from the new vendor version and re-apply the project's change** rather than assuming the old copy still fits. `navigation_user.html` is deliberately kept to a one-line diff so this stays cheap, and a test asserts it has not drifted further.

A fourth fork exists for the same reason but against a different vendor: `templates/admin/room_schedules/room/_o365_tabs.html` shadows the submodule's own copy to add the "Estate links" tab. `TEMPLATES.DIRS` is searched before `APP_DIRS`, so no submodule edit is needed. Re-diff it on a submodule update; `estate/tests/test_room_links.py::TabTemplateDriftTests` fails if it loses one of the vendor's own tabs.

**Why not Unfold's `extra_userlinks` block**, which exists for exactly this purpose: it is filled via `{% block extra_userlinks %}`, reachable only by overriding a template in the inheritance chain. `admin/base_site.html` looks like the hook, but `templates/admin/index.html` extends `admin/base.html` **directly**, so a `base_site.html` override silently misses the dashboard. Covering everything would mean forking Unfold's 48-line `admin/base.html` — a bigger fork than the file we actually want to touch.

**Why each palette needs two ramps.** Unfold uses `--color-primary-500` for text on white (`text-primary-500`) *and* on near-black (`dark:text-primary-500`). No single mid-tone clears 4.5:1 against both, so its stock purple misses on both sides (4.12:1 and 4.30:1) — that is the original accessibility complaint, and it is structural, not a bad hue. Hence two seams:

- **Light ramp** — `UNFOLD["COLORS"]["primary"]` points at `advertising.admin.accent_palette`, resolved per request and emitted into `:root`.
- **Dark overrides** — `advertising.admin.accent_stylesheet` adds `screens/static/screens/css/accent/<slug>.css`, whose `html.dark` selector (specificity 0,1,1) out-ranks that `:root` (0,1,0).

Those CSS files are **generated from `ACCENTS`** — do not hand-edit them; the test suite fails if they drift.

**Unfold signals state with hue, which neutral palettes do not have.** The selected sidebar item is marked `bg-base-100 font-semibold text-primary-600` (`unfold/helpers/app_list.html`) — the background is ~1.05:1 against the sidebar, so selection rides almost entirely on the text being *purple*. Under a neutral accent it vanishes: graphite's `primary-600` is ~1.3:1 against ordinary nav text, leaving font-weight as the only cue. `accent.css` restores it with a left bar plus a stronger row background, which is hue-independent and so also stops selection being conveyed by colour alone (WCAG 1.4.1). **If another piece of chrome looks ambiguous under graphite, suspect the same cause** — find what unfold styles with `text-primary-*` and no other signal.

**The private behaviours depended on**, i.e. the list to re-check on upgrade:

- `_get_value` resolves a dotted-path string **and calls it with the request**. Pre-existing coupling — `SITE_TITLE`/`ENVIRONMENT` already rely on it — that the accent work widens to `COLORS` and `STYLES`.
- `get_config()` deep-merges per key, so `{"COLORS": {"primary": …}}` keeps Unfold's `base` and `font` ramps. Replacing the whole `COLORS` value would drop them.
- `_get_colors` **mutates the dict it returns**, so `accent_palette` must return a fresh `dict(...)`. Sharing the registry's dict would let one request permanently recolour the admin for everyone.
- Dark mode is **class-based** (`html.dark`, set by Alpine on `<html>`). A move to `@media (prefers-color-scheme)` would silently disable every dark override.
- Colours are emitted into `<style id="unfold-theme-colors">` in `unfold/layouts/skeleton.html`.
- Unfold's `.select2-results__option:hover` background also matches select2 *groups*, since a group is an option that contains its children — so hovering one building in the screen form's campus-grouped Building box lit up the whole campus. `estate/static/estate/css/building_picker.css` resets `[role="group"]:hover` by out-ranking that selector, and `estate.tests.test_room_picker` pins the selector so an upgrade that changes it fails.

Unfold ships a **compiled** Tailwind bundle containing only the classes its own templates use, so an arbitrary utility class may simply not exist. Project admin CSS is therefore hand-written against Unfold's custom properties (`accent_switch.css`, `admin_table_links.css`, `recurrence_unfold.css`) rather than composed from utilities.

`uv run python manage.py test screens.tests.test_accent_picker` is the post-upgrade smoke test: it asserts contrast for every palette, checks the rendered page rather than the config, and carries a `UnfoldCouplingTests` class whose whole job is to fail loudly when one of the assumptions above stops holding.

### Estate directory

`estate/` mirrors the University's Learning Spaces Datastore so `Screen.room` can point at a real room, and so the admin can filter and roll up by building.

**`Screen.building` is denormalised on purpose.** It equals `room.building` whenever a room is set, and stands alone only for a screen in no catalogued room. Every building-level question (list filters, the dashboard rollup, the per-building page, the estate building counts) reads `building`, never `room__building`, so building-only screens are included. Two writers keep it in step: `Screen.save()` (skipped for an `update_fields` save that omits `room`, i.e. the heartbeat), and `estate.sync._realign_screens`, which runs after the room upsert and before the sweep, using a queryset `update()` so `last_updated` does not move. **A queryset `.update(room=…)` bypasses `save()` — set `building` alongside it** (as `helpdocs/demo_data.py` does).

**One endpoint, paginated, and flat.** `GET {LSD_API_BASE_URL}/v1/signage/rooms/`, authenticated with a `key:` request header — a feed the LSD team built for this app, returning a `{count, next, previous, results}` envelope. `estate/lsd_requests.py` walks `next` at `page_size=1000` (the upstream cap; larger values are silently clamped) and hands the reconciler one list. gzip is on, via httpx's default `Accept-Encoding`. `LSD_SYNC_TIMEOUT` is a per-page read timeout.

**The walk refuses rather than returning a partial list**, because the reconciler deletes by absence. `count` is pinned from the **first** page and any page reporting a different one aborts the run: a row deleted upstream mid-walk shifts later rows back a position, so a room slides into a page already read and is skipped, and every later page then agrees on the smaller total — only the first page's count exposes it. The run also aborts if the collected rows ≠ that count, if an id repeats across pages, or if `next` leaves the configured scheme/host (the client carries the API key, so it must not follow a URL the response names off-site). All of these are `RuntimeError`, which `sync_estate` retries.

*(Two siblings, both deliberately not used. `/v1/rooms/` is a bare, uncounted array whose `active` is a meaningless legacy string. `/v1/export/rooms/` covers only centrally managed teaching space and flattens the campus names. The signage feed is the authoritative one. Don't switch without re-reading this section.)*

There is no `/buildings/` or `/campuses/` endpoint — campus and building arrive as *strings on every room row* — so `Campus` and `Building` are **derived** from the distinct values across the payload.

- **Campus identity is `campus_lst`**, the internal name ("Central North", not "Central"). `campus_name_short` is stored as `Campus.code` but is emphatically *not* a key: it arrives in mixed case and blank on some rows (and the old feed used `KB` for two campuses). It is resolved by majority vote, blanks not voting. The feed's `campus` field is a third, different thing — a coarser public grouping ("Central" spans three `campus_lst` values), blank on ~47% of rooms and inconsistent within buildings — stored as text on `Room.public_campus` and never keyed on.
- **Building identity is `(campus_lst, building)`.** The campus must be in the key because "Medical School" genuinely exists on two campuses. The consequence to know: **a building renamed upstream becomes a new row**, and the old one is swept once empty. Screens are unaffected — rooms key on their own `lsd_id`.
- **`building_code` is Estates' own code, stored per room, never a key.** It is many-to-many with our building names: some of our names carry several codes (IGMM), some codes cover several of our names (`0228` spans "40 George Sq" and its Lower Hub), and guest/leased buildings have none. Each *room* carries one or none, so it lives on `Room`; `Building.estates_codes` rolls it up. A single column on `Building` would be lossy.

**Reconciliation follows the `sync_o365_rooms` precedent** — delete what nothing depends on, flag what something does — but `_referenced_pks` walks `_meta.related_objects` rather than naming `Screen.room` explicitly, so a future FK into the estate counts automatically. **A room or building a Screen points at is never deleted** — nor a room, building or campus a `LocationGroup` grants, since its M2M is a related object too. A building-only screen on a building renamed upstream therefore keeps the old, flagged building — see `KNOWN_ISSUES.md`. Children are swept before parents so a building emptied this run goes in the same run. A granted *building* that goes stale is usually an upstream rename, which leaves the grant covering nothing; it is flagged (`stale_grants_q()`, the Location groups list's **Needs review**, a superuser dashboard notice), not carried across automatically.

**The safety valve the O365 sync lacks.** The whole feed is fetched before anything is written, and the count check above stops a short read. Behind it, below `LSD_SYNC_MIN_ROOMS` or a shrink past `LSD_SYNC_MAX_SHRINK_PCT` the run still upserts but **skips reconciliation entirely** and logs at ERROR — the second line, for a response that is complete by its own count but wrongly filtered upstream. Refusing to delete is recoverable; deleting is not.

**`Room.active` means "open today"** — derived upstream from the room's start and end dates, which the API does not expose, so it can flip at midnight with no upstream edit and is only as fresh as the last sync. Only an explicit JSON `false` makes a room inactive; anything malformed reads as active, so bad data fails towards no flag. It is displayed and filtered on, and it badges any screen in an inactive room (screen list Room column, `?room_set=inactive`, the per-building page), but **it never hides a room from the picker**: a room opening next month may rightly get its screen now.

**Fields the signage feed does not carry are not modelled.** Moving to it dropped `usage`, `av_type`, `support_group` and `host_key` (migration `0003_signage_feed`); a column the sync can no longer fill would keep its last value for ever and look current. The feed normalises the old literal-`"None"` strings to null, and excludes the test campus; `sync._text()` still folds `"None"` as a cheap defence.

**Two things called Building and Room.** `estate.Building`/`estate.Room` are the University's record; `room_schedules.Building`/`room_schedules.Room` are display configuration created when an operator promotes an O365 mailbox. Keep them apart — importing the estate into the latter would flood the building grid displays, which render `Building.room_set`. `verbose_name` disambiguates them in the admin ("estate building", "estate room"); in code, `from estate.models import Building as EstateBuilding`.

**The link between them is owned by `estate`**, as `BuildingLink`/`RoomLink`, *not* as FK columns on the submodule models. An FK into `estate` from `room_schedules` would make this app a hard requirement of a submodule shared with consumers that do not have it — `fields.E300` at startup, not a missing feature — and would split every change across two repos. `estate/matching.py` scores suggestions (stdlib `difflib` only); nothing is ever linked automatically and no suggestion is pre-selected.

**The estate admins are read-only at `has_*_permission`, not via `readonly_fields`.** `readonly_fields` still renders a Save button and still writes, and an edit here survives only until the next nightly run — a control that silently discards the operator's work. False for superusers too.

**No team scoping, and it is not a judgement call.** Team ownership is conferred by `TeamScopedAdminMixin.save_related` from `request.active_team`; these rows are written by a Celery task, so every one would be created team-less and `scope_to_active_team` would filter them all out for every non-superuser. Scoping happens one level up, on the `Screen` that points at the room. Read access is controlled on the correct axis, by `estate.view_*` permissions. **Location scoping does apply** (`ReadOnlyMirrorAdmin.get_queryset`) — it keys on grants held by the user, not on ownership stored on the row, so the Celery problem does not arise. Pages that draw on the whole estate — `room_links_view`, the link admins, `estate_sync_now_view` — require `sees_all_locations` instead.

Two traps worth knowing:

- The screen form picks a room in two steps (`estate/picker.py`): a local, campus-grouped **Building** select (`ScreenAdminForm` declares it over the `Screen.building` model field), then a **Room** autocomplete served by `RoomPickerJsonView` (Django's `AutocompleteJsonView` narrowed to one building, labels `name (lsd_id)` because the datastore holds a few same-named duplicates). That view checks `has_view_permission` on **`RoomAdmin`**, so a user with `screens.change_screen` but no `estate.view_room` can pick a building but gets "The results could not be loaded" for rooms. Grant the estate view permissions alongside screen editing. Two quirks of the picker are deliberate: `RoomPickerWidget.value_omitted_from_data` returns `False`, because the disabled-until-a-building-is-chosen select is not submitted and `Screen.room`'s default would otherwise make Django keep the old room; and its media repeats `autocomplete.js`, because Django only orders media files that share a list.
- A related list filter that renders no options still has its lookup parameter popped by `ChangeList.get_filters`, so a hidden filter does not merely fail to render — it **silently ignores** `?building__id__exact=N` and shows everything. `EstateRelatedFilter.has_output()` overrides that whenever a value is selected, because the per-building page and the dashboard both link with exactly that parameter.

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

All `screens` models are split into individual files under `screens/models/` and re-exported from `screens/models/__init__.py`. The `room_schedules` and `estate` models follow the same pattern under `room_schedules/models/` and `estate/models/`.

`helpdocs` is the exception: a single `models.py` holding one unmanaged model that exists only to carry the `view_technical_docs` permission. It has no table and no rows.
