# Known issues

Things found but deliberately not fixed yet, each with enough detail to pick up cold.
Remove an entry when it is fixed.

Numbers are append-only so existing references stay valid; they are not a
priority order, and gaps mean an entry was fixed and removed.

Nothing left here is actively mis-serving screens. Issue 9 was — schedule rules
evaluated in the UTC wall clock, so every rule fired an hour late throughout BST
and day-of-week patterns fired on adjacent days — and it is fixed.

Found 2026-08-04 while diagnosing the admin bulk-delete 500 (fixed — see the
`delete_queryset` override in `TeamScopedAdminMixin`, `screens/admin.py`).

---

## 1. No logging config — production discards its own tracebacks

**Symptom.** A 500 in production leaves no traceback anywhere. The bulk-delete bug above had
to be found from nginx access logs and a production shell session rather than from anything
Django produced.

**Cause.** There is no `LOGGING` in `advertising/base_settings.py` or in the deploy repo's
`docker/advertising/settings.py`. With `DEBUG=False`, Django's default config routes
`django.request` ERROR records to a `console` handler filtered out by `require_debug_true`,
and to `mail_admins`, which is inert because `ADMINS` and email are unset. uwsgi logs only
the request line.

**Re-verified 2026-08-12 and confirmed as written.** No `LOGGING`, `ADMINS`, `EMAIL_BACKEND` or
`EMAIL_HOST` exists in any of the three settings layers, and `settings.ADMINS` is `[]`. Emitting
the exact record Django uses for a 500 (`django.request` ERROR with `exc_info`) under Django's
`DEFAULT_LOGGING` produces a full traceback on stderr at `DEBUG=True` and **nothing at all** at
`DEBUG=False`. Note the `django` logger does have two handlers attached, so Python's last-resort
stderr fallback never engages — the record is found, handled, and discarded by both. That is
what makes this different from issue 3's cleanup errors, which do reach the log.

**Approach.** Log to stdout/stderr, not to a file inside the container: uwsgi, celery and
nginx already stream there so there is one place to look; a file inside the container has no
volume and dies on rebuild; and Docker rotates streams natively. Per the three-layer settings
rule in `CLAUDE.md` this touches four files plus compose.

`advertising/base_settings.py` — plain defaults, no `os.environ` reads:

```python
LOG_LEVEL = "INFO"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose", "level": LOG_LEVEL},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        # Pinned at ERROR regardless of LOG_LEVEL — this is the logger carrying
        # 500 tracebacks, and losing it is what made the bulk-delete bug hard to find.
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        # Pinned so LOG_LEVEL=DEBUG doesn't start logging every SQL query.
        "django.db.backends": {"level": "WARNING"},
    },
}
```

`advertising/settings.sample.py` — a commented note that `LOG_LEVEL` exists.

Deploy repo `docker/advertising/settings.py` — the env read, alongside `MAX_IMG_WIDTH`:

```python
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOGGING["handlers"]["console"]["level"] = LOG_LEVEL
LOGGING["root"]["level"] = LOG_LEVEL
LOGGING["loggers"]["django"]["level"] = LOG_LEVEL
```

Deploy repo `.env.sample` — a documented `LOG_LEVEL=INFO` block.

Deploy repo `docker-compose.yml` — bound the log files with a YAML anchor applied to all six
services (`nginx`, `advertising`, `worker`, `beat`, `redis`, `db`):

```yaml
x-logging: &default-logging
  driver: json-file
  options:
    max-size: "10m"
    max-file: "5"
```

While in that file, drop the obsolete top-level `version:` key — compose warns on every run.

**Disk growth.** Docker's `json-file` driver has no default size limit, so
`/var/lib/docker/containers/<id>/<id>-json.log` already grows without bound, fed by uwsgi
request lines, nginx access logs and celery output. The anchor above caps each container at
50 MB, roughly 300 MB for the stack. The logging config itself adds almost nothing: at `INFO`
Django emits essentially only 500 tracebacks, 1–3 KB each. Rotation applies only on container
**recreation** (`docker compose up -d`, not `restart`) and does not retroactively trim an
existing oversized file — that goes away with the old container.

**Turning it down.** `LOG_LEVEL=ERROR` in `.env`, then
`docker compose up -d advertising worker beat`. Use `up -d`, not `restart` — environment
variables are baked in at container creation time.

**Reading it.**

```bash
docker compose logs -f advertising
docker compose logs advertising | grep -B2 -A40 Traceback
docker compose logs nginx | grep -E ' 50[0-9] '   # cross-check the status code
```

**Deployment order — important.** The deploy override mutates `LOGGING`, so it raises
`NameError` at startup if the `advertising` submodule still points at a commit without the
dict. The submodule tracks `learningspacestechnology/signage.git` branch `master`, and
`update.sh` runs `git submodule update --remote`: push this repo's `master` **first**, then
the deploy repo, then one `./update.sh` picks up both. The reverse order takes the site down.

---

## 2. `TeamAdmin` refuses a blocked delete in the wrong vocabulary

**This entry previously claimed bulk delete returns a 500. It does not — retested 2026-08-12.**
It was a predicted second bug rather than an observed one, and the prediction was wrong.

Actual behaviour, as a superuser:

| Case | Confirmation page | After confirming | Deleted? |
|---|---|---|---|
| Team owns a playlist | 200, no confirm button | 403 | no |
| Team has a member | 200, no confirm button | 403 | no |
| Clean team | 200 | 302 | yes |
| Single-object delete form, blocked team | — | 403 | no |

Nothing crashes and nothing is wrongly deleted. The guard holds on both paths.

**Cause of the real, much smaller defect.** The old entry assumed `delete_selected` only asks
`has_delete_permission(request, obj=None)`. It does not: `get_deleted_objects` asks it for
*each* object (`django/contrib/admin/utils.py:132`). Ours returns `False` for a blocked team, so
the team lands in `perms_needed`, the page renders Django's *"Cannot delete team … your account
doesn't have permission to delete the following types of objects"* with no confirm button, and a
hand-crafted POST hits `raise PermissionDenied` (`django/contrib/admin/actions.py:43-44`).
`delete_queryset` / `delete_model` are never reached in this path, so the `ValidationError` the
old entry blamed never fires.

So the operator is refused *and* told something — just in the wrong vocabulary. The page blames
their account's permissions when the real reason is that the team still owns content or has
members, which is information they could act on.

**Fix.** Still the `get_deleted_objects` override, but now for wording rather than
crash-avoidance. One ordering detail to save re-deriving: `delete_selected` guards its delete
branch with `not protected` (`actions.py:43`), so putting blocked teams into `protected` is by
itself enough to stop the 403 on a crafted POST. But `perms_needed` is populated independently,
so the misleading permission sentence stays unless `has_delete_permission(request, obj)` also
stops returning `False` — let `protected` carry the refusal instead. Leave the `pre_delete`
signal in `screens/models/team.py` alone; it guards shell and cascade deletes and
`screens/tests/test_team_scoping.py` depends on it raising.

**Priority: cosmetic.** It refuses correctly today, and no data is at risk.

**Help docs.** `helpdocs/content/technical/users-and-teams.md` says the guard "can't be bypassed
with a bulk action". That is true and now verified by test, so the correction the old entry
asked for is not needed.

---

## 3. Media orphans — original diagnosis was wrong; only edge paths leak

**This entry previously claimed `/srv/media` grows monotonically because nothing deletes files
on `Source` delete. That is false — retested 2026-08-12.** `django_cleanup.apps.CleanupConfig`
is in `INSTALLED_APPS` (`base_settings.py:51`) and the deploy does not override
`INSTALLED_APPS`, so it is active in production. It registers on `post_init`, `pre_save`,
`post_save` and `post_delete`, and it handles every path the old entry worried about:

| Path | File removed? |
|---|---|
| `source.delete()` | yes |
| `Source.objects.filter(...).delete()` (bulk) | yes |
| Replacing `Source.file` and saving | yes (old file) |
| `screens.tasks.cleanup_sources` periodic task | yes |

**Beware when re-verifying this.** django-cleanup defers deletion to
`transaction.on_commit()`, which never fires inside `TestCase`'s rolled-back transaction, so a
naive probe shows every file surviving and looks exactly like the bug described above. That is
what produced the original wrong diagnosis. Use `TransactionTestCase`, or
`self.captureOnCommitCallbacks(execute=True)`.

**The residual, much smaller issue.** django-cleanup only reacts to signals, so files can still
be stranded by paths it cannot see, and nothing can audit or reclaim them:

- uploads whose transaction later rolled back — the file is written before commit, and nothing
  was deleted for django-cleanup to react to;
- `Source` rows deleted through a data migration using `apps.get_model`, since signals bind to
  the concrete class and do not fire for historical models (the same property `0032` relies on);
- anything predating django-cleanup's addition, or left by a restore that put the database and
  `/srv/media` out of step.

**Correction to the old permission note.** It said a media-directory permission problem "would
surface on upload, never on delete". The opposite half is now wrong: deletes do touch the
filesystem. `docker-compose.yml` bind-mounts `./media:/srv/media`, which masks the Dockerfile's
build-time `chown -R advertising:advertising /srv/media` with the host directory's ownership, so
a mismatch breaks both. django-cleanup catches the failure and calls `logger.exception`
(`django_cleanup/handlers.py:112-116`) rather than raising, so it reaches `docker compose logs`
only via Python's last-resort stderr handler — easy to miss until issue 1 is done.

**Fix, if it is ever worth it.** The `prune_orphaned_media` management command described
before — list files in `MEDIA_ROOT` unreferenced by any `Source.file`, print them with a total
size, delete only with `--delete`, dry-run by default. It is now an occasional audit tool rather
than the primary cleanup mechanism, so it does **not** belong in `CELERY_BEAT_SCHEDULE`:
scheduling a deleter against a race it cannot see is worse than the leak. Check whether real
orphans exist before writing it:

```bash
docker compose exec advertising python manage.py shell -c \
  "from screens.models import Source; import os; from django.conf import settings; \
   db={s.file.name for s in Source.objects.exclude(file='')}; \
   disk={os.path.relpath(os.path.join(r,f), settings.MEDIA_ROOT) \
         for r,_,fs in os.walk(settings.MEDIA_ROOT) for f in fs}; \
   print(len(disk-db), 'orphans of', len(disk), 'files')"
```

---

## 4. Over-long names crashing the admin log — does not happen

**This entry was wrong. Retested 2026-08-12; nothing to fix.** It was latent and unobserved,
which is why it survived unchallenged.

The premise was sound as far as it went: `Source.name` and `Playlist.name` are unbounded
`TextField`s (`source.py:32`, `playlist.py:23`) and `django_admin_log.object_repr` really is a
`varchar(200)`. The conclusion did not follow. `LogEntryManager.log_action` truncates before the
insert — `object_repr=object_repr[:200]` (`django/contrib/admin/models.py:42`) — and every admin
write goes through it (`django/contrib/admin/options.py:926,943,961`).

Verified end to end: adding a `Source` with a 400-character name through the admin returns 302,
creates the object, and writes a `LogEntry` whose `object_repr` is exactly 200 characters. The
database never sees an over-length value, so the MariaDB-versus-SQLite distinction the entry
leaned on is irrelevant.

**Optional, and a preference rather than a fix.** `max_length=200` on the two fields would still
buy form validation, a saner widget, and readable list displays. Worth doing only if someone is
already in those models.

**Knock-on.** Migration `0032`'s `NAME_MAX_LENGTH = 150` truncation cites this issue as its
reason. The truncation itself is fine — auto-generated names stay readable — but the stated
justification was wrong, and the comment has been corrected in place.

---

## 5. Ticker screens cannot play screen-level interspersed content

**Symptom.** A screen with the ticker enabled ignores its own **Interspersed playlist**. The
playlist's own interspersed content still plays. Currently unreachable rather than fixed —
`ScreenAdmin` hides the two fields while `ticker_enabled` is set (see
`_interspersed_blocked_by_ticker`), so an operator can no longer configure the combination.

**Cause.** `screens/views.py`. A ticker screen gets `_ticker_redirect_payload`, a single
iframe pointing at `/screen_wrapper/<id>`. That template's inner iframe loads
`/playlist/<id>`, which nginx serves as the Vue player, which fetches
`/api/playlist/<id>` → `view_playlist_json` → `render_playlist_json(playlist)` with no
`screen` argument. The screen's identity never crosses into the inner frame, so
`interspersed.screen` is always `null`. Predates the move to playlist-based interspersed
content; the old single-source field was lost the same way.

**Fix.** Make `view_playlist_json` screen-aware. Resolve the caller with the existing
`get_screen(request)` and pass `screen=screen` **only** when
`screen.schedule.get_playlist().pk == playlist_id`. That guard matters: without it an
arbitrary `/api/playlist/<id>` fetch would leak another screen's configuration. Then remove
the admin guard and its tests in `screens/tests/test_admin_interspersed.py`, and put the
demo data's screen-level interspersed setting back on the ticker screen so `screen-form` and
`ticker-fieldset` can share one screen again (`helpdocs/demo_data.py`,
`helpdocs/screenshots.py`).

**Ruled out.** Pointing the inner iframe at `/screen/<id>` instead: that re-enters the ticker
branch in `view_screen_json` and nests wrappers until the browser dies.

**Tests.** `test_ticker_inner_playlist_json_includes_the_screen_stream`, and one asserting a
plain `/api/playlist/<id>` fetch from an unrelated IP still reports `interspersed.screen` as
`null`.

---

## 6. Timezone consistency: naive `datetime.now()`

**Symptom.** `RuntimeWarning: DateTimeField ... received a naive datetime while time zone
support is active` on most test runs, and on every content query in production.

**Cause.** `USE_TZ = True` has been set since `f36c997` (`advertising/base_settings.py`), but
two call sites still build naive values: `screens/models/playlist.py:64` (`get_sources`) and
`screens/tasks.py:9` (`cleanup_sources`). Upstream fixed these in `c80aa01`, which this branch
has not taken.

**This entry previously listed a third site, `schedule_rule.py:32` (`is_expired`), as mere
warning noise. That was wrong twice over** — it was a live `TypeError`, not a warning, and
upstream's `c80aa01` did not fix it either. `RecurrenceField` serialises `dtstart` as UTC, so
any rule saved with one deserialises *aware*, and `.after(<naive cutoff>)` raised
`can't compare offset-naive and offset-aware datetimes`. Because `cleanup_schedule` filters
with a lambda over every rule, one such row aborted the whole task. Fixed alongside issue 9 by
normalising both the cutoff and the `dtstart`, and covered by
`screens/tests/models/tests_schedule_rule.py`.

**The two remaining sites are not currently wrong**, which is why they have survived. Django sets
`os.environ["TZ"]` from `TIME_ZONE` and calls `time.tzset()`
(`django/conf/__init__.py:254-264`), so `datetime.now()` returns Europe/London local time and
Django interprets naive values in the same zone — the instant lands correctly. What they cost:
warning noise, an ambiguous hour every autumn when the clocks go back, and a trap for
`aggregate_last_updated` in `screens/views.py`, whose `max()` raises
`TypeError: can't compare offset-naive and offset-aware datetimes` the moment a naive value
reaches it.

**That safety rests on the container carrying tzdata, so verify before relying on it.** Neither
`docker-compose.yml` nor `.env.sample` sets `TZ`, and the deploy's
`docker/advertising/settings.py` does not override `TIME_ZONE`, so production takes
`Europe/London` from `base_settings`. Django's `tzset()` call then only resolves it if
`/usr/share/zoneinfo` is populated. The `python:3.12` base image is Debian and ships tzdata, so
this should hold — but if it ever did not, `datetime.now()` would return UTC while Django kept
interpreting naive values as Europe/London, and every one of these sites would silently land an
hour out during BST. Confirm with:

```bash
docker compose exec advertising python -c \
    "import datetime; print(datetime.datetime.now(), datetime.datetime.now(datetime.UTC))"
```

**Do not blanket-swap `datetime.now()` to `timezone.now()`.** The schedule bug that was issue 9
was the *opposite* problem — aware UTC where naive local is required — and some naive uses are
deliberate and correct:

- `room_schedules/o365_requests.py:66` compares `now.hour` against `HOUR_BREAK_POINT`. That
  needs the local wall clock and would break on `timezone.now()`, which yields the UTC hour.
- `book_adhoc` in the same module keeps `datetime.now()` on purpose: O365 handles the zone
  server-side from the `timeZone` field, and switching would shift the wall-clock time sent.

The rule is which *kind* of time each site wants — instant, or local wall clock — not which
function looks more modern.

**The Celery beat settings that used to be listed here are done**, alongside issue 9.
`DJANGO_CELERY_BEAT_TZ_AWARE = True` was the half that mattered: at `False`, `ModelEntry` wrote
`PeriodicTask.last_run_at` as naive UTC, which Django read back as `Europe/London` — an hour
early for the whole of BST. `CELERY_ENABLE_UTC = False` was added for upstream parity only;
`Celery.timezone` consults it solely when `conf.timezone` is falsy, and `CELERY_TIMEZONE` is
set, so it does not pick the zone. See the comments on both keys in `base_settings.py`.

---

## 7. Dependency bump — Django, Unfold, and everything else

**Symptom.** None yet. Everything is pinned exactly and nothing has moved for a while:
`django==4.2.29`, `django-unfold==0.82.0`, `celery[redis]==5.3.6`, `django-celery-beat==2.5.0`,
`django-celery-results==2.6.0`, `django-recurrence==1.14`, `pillow==12.1.1`. Upstream has
already bumped Django (`a650fd8`).

**Take it as an isolated `uv` change, not by merging upstream.** `upstream/master` carries
`screens/migrations/0023_alter_playlist_parents_alter_source_playlists`, which collides with
this branch's `0023`–`0032`; a merge needs the numbers reconciling by hand. Its content is
help_text-only `AlterField`s already superseded by our `0030`, so there is nothing to gain.
Of upstream's 8 unmerged commits, `dc1b5f3` (recurrence widget) is already done here
independently — `recurrence_unfold.css` is byte-identical and the `Media` block is at
`screens/admin.py:213` — and `c57cd51` (interspersed) was ported in this branch's own commit.
That leaves only the Django bump (`a650fd8`, which carries both `DEFAULT_AUTO_FIELD` and the
`USE_L10N` removal) as a real gap — `c80aa01` and `4d9c07d` were taken with issue 9.

**Checklist for when you do it, in order:**

1. **Do issue 10 (`DEFAULT_AUTO_FIELD`) first.** Bumping without it invites the natural fix —
   Django's `BigAutoField` default — which would generate an `AlterField` on every primary key
   in the project.
2. **Delete `USE_L10N = True`** (`base_settings.py:338`). Deprecated in Django 4.0, *removed*
   in 5.0, so it is a hard blocker. It is the **only** one I found: I checked for
   `django.utils.timezone.utc`, `index_together`, `providing_args`, `DEFAULT_FILE_STORAGE`,
   `STATICFILES_STORAGE`, `force_text`, `ugettext`, `NullBooleanField` and
   `django.conf.urls.url`, and none are present. (The `timezone.utc` hits in
   `screens/tests/models/` and `room_schedules/o365_requests.py` are the stdlib
   `datetime.timezone`, not Django's.) No `STORAGES`/`*_STORAGE` settings are configured
   either, so the 4.2 storage migration is a no-op here.
3. **Unfold is the real risk, not Django.** This project overrides two Unfold internals —
   `templates/unfold/helpers/userlinks.html` (36 lines; the team switcher, which is this
   project's own mechanism rather than Unfold's unconfigured `SITE_DROPDOWN`) and
   `templates/unfold/helpers/unauthenticated_header.html` (12 lines) — plus
   `templates/admin/login.html` (100) and `templates/admin/index.html` (149). An override
   silently keeps rendering the old markup when the upstream template moves on. Diff each
   against the new version's original before assuming the admin still works.
4. **Re-capture help screenshots after an Unfold bump**, and expect churn. The `ticker-fieldset`
   shot in `helpdocs/screenshots.py` drives both a `<details>` toggle and Django's `collapse.js`
   Show/Hide because which one Unfold renders is version-dependent — that `run_js` is
   version-sensitive by construction. Its `clip='fieldset.collapse'` also assumes the ticker is
   the only collapsible fieldset on the screen form.
5. **Fold in the Celery beat timezone settings** (issue 6) if `celery` or `django-celery-beat`
   move, since that is where `CELERY_ENABLE_UTC` and `DJANGO_CELERY_BEAT_TZ_AWARE` bite.
6. **Watch the deploy's in-place mutation of `CELERY_BEAT_SCHEDULE`.** The deploy override does
   `del CELERY_BEAT_SCHEDULE['build-schedule-hourly']` and then inserts
   `build-schedule-often`. Renaming or removing that key in `base_settings.py` raises `KeyError`
   at container start, and the `advertising` submodule pointer must advance to a commit
   containing the change *before* the deploy repo is updated — the same ordering hazard issue 1
   documents for `LOGGING`. Nothing else in the bump touches it, but a beat version change is
   exactly when someone reorganises that dict.
7. **Fix issue 11 first if you want CI to gate on `makemigrations --check`** — it currently
   reports a phantom pending migration on every developer machine, which makes it useless as a
   guard for exactly the kind of model drift a framework bump causes.

**Checked against the deploy:** `docker/advertising/settings.py` overrides none of `USE_L10N`,
`DEFAULT_AUTO_FIELD`, `USE_TZ`, `TIME_ZONE`, `CELERY_ENABLE_UTC` or
`DJANGO_CELERY_BEAT_TZ_AWARE`, so all of the settings work above lands in `base_settings.py`
alone, with no `.env.sample` entry needed. Per the three-layer model in `CLAUDE.md`, only add a
deploy-side `os.getenv` if a value should vary per site — none of these should.

---

## 8. Watch — intermittent 502 on room schedule polling

One occurrence in the production nginx log, 2026-08-03 15:22:
`GET /event_schedules/2/3/state_hash` → 502. A 502 means uwsgi refused the connection or the
worker died, so Django logs nothing regardless of configuration. May simply have been a deploy
restart. Not worth chasing on a single sample — once issue 1 is done, check whether it recurs
and whether anything appears in the app log alongside it.

**Still live, checked 2026-08-12.** The route exists and matches the observed path exactly:
`path('<int:venue_id>/<int:room_id>/state_hash', room_state_hash, ...)`
(`room_schedules/urls.py:36`, so `/event_schedules/2/3/state_hash` is venue 2, room 3). Three
room templates still poll it — `room_screen.html:642`, `room_screen_uoe.html:287`,
`room_tablet.html:713` — so this is a hot endpoint, not a stale one, and the watch is still
worth keeping. The 502 itself cannot be reproduced or ruled out from a dev checkout; it needs
the production nginx log.

---

## 10. `DEFAULT_AUTO_FIELD` unset — 19 warnings on every command

**Symptom.** Every single `manage.py` invocation prints 19 `models.W042` warnings, one per
model, burying whatever you actually ran the command to see.

**Cause.** `DEFAULT_AUTO_FIELD` is not set in `advertising/base_settings.py`, so Django warns
for every model that does not declare an explicit primary key type.

**Fix.** One line, no migration:

```python
# Preserve the legacy AutoField PK type; existing DBs were created before
# Django 3.2's switch to BigAutoField.
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
```

Upstream added exactly this in **`a650fd8`** ("chore: bump django") — *not* `c80aa01`, as this
entry said before; `c80aa01`'s `base_settings.py` diff is only the timezone keys. `a650fd8` is
also where `USE_L10N` is deleted, so issue 7's step 2 and this entry come from the same commit.
**It must be `AutoField`, not Django's `BigAutoField`
default** — these tables predate Django 3.2, and `BigAutoField` would generate an `AlterField`
on every primary key in the project, plus every FK that references them. Do this before the
dependency bump (issue 7).

`base_settings.py` is the only file to touch: the deploy override does not set it, and it should
not vary per site, so no `.env.sample` entry is wanted.

---

## 11. `makemigrations --check` always reports a phantom pending migration

**Symptom.** `uv run python manage.py makemigrations --check --dry-run` reports a pending
`alter_source_file` on a clean tree, so it cannot be used as a CI guard against model drift.
The generated migration differs per developer, so committing it just moves the problem.

**Cause.** `Source.file`'s `help_text` is an f-string over `MAX_IMG_WIDTH`/`MAX_IMG_HEIGHT`
(`screens/models/source.py:36`), so those values are baked into migration state. Migration
`0019` recorded 1920x1080 from `base_settings`; the dev `settings.py` default is 2160x3840, so
the autodetector sees a permanent diff.

**These dimensions are deliberately per-deployment, so this is not just a dev-machine quirk.**
The deploy sets `MAX_IMG_WIDTH = int(os.getenv("MAX_IMG_WIDTH", "1920"))` and both keys are
documented in `.env.sample:87-88`. Any site that tunes them gets a `help_text` differing from
migration state as well. Nothing breaks at runtime — `help_text` is not enforced — but no value
can be "correct" in a migration, which is what makes this unfixable by editing the recorded
migration.

**A related but separate point about the import.** `screens/models/source.py:6` does
`from advertising.settings import MAX_IMG_WIDTH, MAX_IMG_HEIGHT`, importing the settings
*module* rather than going through `django.conf.settings`. In production this still resolves
correctly, because the Dockerfile copies the deploy override *onto* that exact module
(`ADD docker/advertising/settings.py advertising/.`), so `advertising.settings` **is** the
production settings file. What it does break is `DJANGO_SETTINGS_MODULE`: pointing it at any
other module leaves these names reading `advertising/settings.py` regardless. That is why
`advertising.screenshot_settings` does not isolate them, and why `makemigrations --check` still
reports the drift under that module.

**Fix.** Routing through `django.conf.settings` is necessary but not sufficient — the f-string
is evaluated at class-definition time, so the value would still be baked in. The dimensions have
to leave migration state altogether: make the `help_text` lazy with
`django.utils.text.format_lazy`, or drop them from `help_text` and surface them in the form or
the upload validation message instead. Only then is `makemigrations --check` usable as a CI
gate.

**Same import style elsewhere, worth auditing in the same pass:** `screens/forms.py:6`,
`screens/views.py:11`, `screens/utils.py:3` and `advertising/urls.py:22`. None currently
misbehave, for the same reason as above, but they carry the same `DJANGO_SETTINGS_MODULE`
blind spot.

---

## 12. A schedule rule with no day selected silently never fires

Found 2026-08-17 while fixing issue 9.

**Symptom.** An operator ticks **Weekly** under Occurrences, selects no days, and saves. The
rule looks fine in the admin, its times are right, and it never plays. Same for **Monthly**
with no day-of-month.

**Cause.** The admin's recurrence widget writes no `DTSTART` — `recurrence-widget.js` never
emits one, so a saved rule is a bare `RRULE:FREQ=WEEKLY`. `Schedule.get_playlist()` therefore
falls back to `normalized_dtstart = stored_dtstart or ref_start`, anchoring the pattern on
*today*. A weekly pattern anchored on today next occurs in seven days, which is never inside
the one-day window being tested, so the rule can never match. A pattern that names its days
(`BYDAY=MO,WE,FR`, which is what the widget writes as soon as you tick a day) is unaffected,
because the named days pin the phase regardless of the anchor.

**Not a regression.** The pre-issue-9 code had the same hole, reached differently — it anchored
on *yesterday*. Pinned by `test_a_rule_with_no_day_selected_never_fires` in
`screens/tests/models/tests_schedule.py` so the behaviour is documented rather than accidental.

**Fix.** Anchor on the rule's own `starts` date, which the operator has already set and which
does not move:

```python
normalized_dtstart = stored_dtstart or datetime.combine(rule.starts, time.min)
```

Keep `ref_start`'s `-= timedelta(seconds=1)`; `time.min` lands occurrences exactly on midnight,
which `between()` excludes. **This changes behaviour for existing rows** — a bare-weekly rule
that has never fired would start firing on `starts`'s weekday — so it needs its own tests and a
line in the release note rather than being slipped in.

**Better still, refuse it at the form.** A recurrence that cannot resolve to any day is not
something an operator ever means; validating it in `ScheduleRule.clean()` turns a silent
non-event into a message at the point of the mistake. Upstream carries the same fallback, so
report whichever way this goes.
