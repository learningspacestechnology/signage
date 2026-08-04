# Known issues

Things found but deliberately not fixed yet, each with enough detail to pick up cold.
Remove an entry when it is fixed.

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

## 2. `TeamAdmin` bulk delete returns 500

**Symptom.** Bulk-deleting a team that still has members or owned objects gives a 500 instead
of the intended refusal message.

**Cause.** `screens/admin.py`, `TeamAdmin`. `has_delete_permission(request, obj=None)` returns
`True` for a superuser when `obj is None`, which is exactly how `delete_selected` asks. The
action then reaches `delete_queryset` → `delete_model`, which raises a bare `ValidationError`
that the admin does not catch. Distinct from the bulk-delete bug already fixed: `TeamAdmin`
does not use `TeamScopedAdminMixin` and overrides `delete_queryset` to loop per object, so it
never touches `.distinct()`.

**Fix.** Override `get_deleted_objects` and put blocked teams into the returned `protected`
list. That is Django's own hook — it makes the confirmation page explain the refusal and hides
the "Yes, I'm sure" button, covering the single-object and bulk paths identically. Keep
`delete_queryset`/`delete_model` as a backstop but convert the `ValidationError` into
`self.message_user(..., level=messages.ERROR)` rather than raising. Leave the `pre_delete`
signal in `screens/models/team.py` alone — it guards shell and cascade deletes, and the tests
in `screens/tests/test_team_scoping.py` depend on it raising.

**Help docs.** `helpdocs/content/technical/users-and-teams.md` says the guard "can't be
bypassed with a bulk action" — true, but the operator currently sees a crash. Reword to
describe what they will actually see.

---

## 3. Orphaned media files accumulate forever

**Symptom.** `/srv/media` grows monotonically; deleted content leaves its file behind.

**Cause.** Nothing removes the file. There is no `post_delete` cleanup — the `pre_delete`
receiver in `screens/models/source.py` only bumps playlist timestamps — and Django has not
auto-deleted `FileField` files since 1.3. The periodic expired-source cleanup in
`screens/tasks.py` compounds it by bulk-deleting sources on a schedule.

Note this also means a media-directory permission problem would surface on **upload**, never
on delete.

**Fix.** A `prune_orphaned_media` management command under `screens/management/commands/`. It
lists files in `MEDIA_ROOT` unreferenced by any `Source.file`, prints them with a total size,
and deletes only when given `--delete`; dry-run is the default. Auditable and safe against a
rolled-back transaction, unlike a `post_delete` receiver. Can join `CELERY_BEAT_SCHEDULE` once
trusted.

**Tests.** Temporary `MEDIA_ROOT` with one referenced and one orphaned file: dry-run reports
one orphan and deletes nothing; `--delete` removes only the orphan.

---

## 4. Over-long names crash any logged admin action

**Symptom.** Latent, not yet observed. Adding, changing or deleting a `Source` or `Playlist`
whose name exceeds 200 characters would 500 in production.

**Cause.** `Source.name` and `Playlist.name` are unbounded `TextField`s, but the admin writes
`str(obj)` into `django_admin_log.object_repr`, a `varchar(200)`. Under MariaDB's strict mode
that raises `DataError: Data too long`. SQLite does not enforce lengths, so it never appears
in development.

**Fix.** Add `max_length=200` to both fields. For `TextField` this drives form validation and
the widget without altering the MySQL `longtext` column, so the generated migration should be
a no-op at the database level — confirm during implementation rather than assuming. Check for
existing offenders first:

```python
from django.db.models.functions import Length
Source.objects.annotate(n=Length("name")).filter(n__gt=200).values_list("id", "n")
Playlist.objects.annotate(n=Length("name")).filter(n__gt=200).values_list("id", "n")
```

**Help docs.** Mention the limit in `helpdocs/content/users/content.md` and `playlists.md`.

---

## 5. Watch — intermittent 502 on room schedule polling

One occurrence in the production nginx log, 2026-08-03 15:22:
`GET /event_schedules/2/3/state_hash` → 502. A 502 means uwsgi refused the connection or the
worker died, so Django logs nothing regardless of configuration. May simply have been a deploy
restart. Not worth chasing on a single sample — once issue 1 is done, check whether it recurs
and whether anything appears in the app log alongside it.
