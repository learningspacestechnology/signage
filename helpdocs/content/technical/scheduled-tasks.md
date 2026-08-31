# Background jobs

Several things happen on a timer rather than when someone clicks something. This
page says what runs, when, and what it changes — so you can tell "waiting for a
job" apart from "actually broken".

## What runs

| Job | Default schedule | What it does |
|---|---|---|
| Clean up content | {{ config.CONTENT_TASK_MINUTES }} | Permanently deletes content past its expiry date, and its file |
| Update playlists | {{ config.CONTENT_TASK_MINUTES }} | Marks playlists as changed when a piece of content has just become valid, so screens pick it up |
| Clean up schedule rules | {{ config.CONTENT_TASK_MINUTES }} | Deletes schedule rules whose repeating pattern has finished for good |
| Pull room bookings | {{ config.ROOM_EVENT_SCHEDULE }} | Fetches today's bookings for every room with a calendar address |
| Clean up old events | {{ config.ROOM_CLEANUP_SCHEDULE }} | Deletes bookings more than two days old |
| Sync O365 rooms | {{ config.ROOM_SYNC_SCHEDULE }} | Rebuilds the tenant room inventory and flags problems |
| Check screens | {{ config.SCREEN_CHECK_SCHEDULE }} | Pings screens that have stopped reporting, and records status changes |
| Clean up status history | daily at 03:30 | Deletes screen status changes older than {{ config.SCREEN_HISTORY_DAYS }} days |

!!! warning "Expiry deletes, it doesn't hide"
    The content cleanup job removes the record **and the uploaded file**. There is
    no undo and no recycle bin. Anyone relying on **Expires at** for seasonal
    content should be told to clear the date instead of letting it pass.

## Where to look

**Periodic Tasks** lists what is scheduled and lets you change it. **Task
Results** shows what has actually run, with status and any error.

![The periodic task list](screenshot:periodic-tasks)

The schedules above are defaults; a deployment can override them, so treat
**Periodic Tasks** as the source of truth for what is really running.

## Changing a schedule

1. Go to **Periodic Tasks** and open the task.
2. Change its schedule. Four kinds are available:
    - **Interval** — every N seconds/minutes/hours. Simplest.
    - **Crontab** — a specific time of day or day of week.
    - **Solar** — relative to sunrise/sunset. Not used here.
    - **Clocked** — once, at one moment. Pair with **One-off task**.
3. Save.

Changes take effect without a restart — the scheduler reads them from the
database.

## Turning a task off

Untick **Enabled** rather than deleting the task. Deleting loses its
configuration, and a redeploy may recreate it with defaults, silently undoing
your change.

Be careful what you disable:

- Disabling **Pull room bookings** freezes every room display at its last known
  state. The screens keep working and keep showing stale bookings, which is worse
  than showing nothing.
- Disabling **Clean up content** means expired content keeps playing.
- Disabling **Update playlists** means content with a future start date never
  appears.
- Disabling **Check screens** does not break status — online/offline still work,
  because they are read from the heartbeat live. What stops is the **Needs
  attention** state and the status history, so every failing display looks
  equally dead and nothing records when it started. See
  [Screen reachability checks](help:screen-reachability).

## Running something now

**Sync O365 rooms** has a button in the interface — **Sync O365 rooms now** on
either O365 rooms tab. See [O365 rooms](help:o365-rooms).

The others have no button. To force one, set it as a **one-off clocked task** for
a moment shortly in the future, let it fire, then restore the original schedule.
Or simply wait — they all run at least daily.

## Reading Task Results

Each run records its status, its return value, and a traceback if it failed.

- **SUCCESS** — ran to completion.
- **FAILURE** — raised an error; the traceback is recorded.
- **RETRY** — failed and will be attempted again. The room sync retries with a
  backoff, so a single retry is not a problem.

Nothing recorded at all for a task that should have run means the scheduler or
the worker isn't running. That's a deployment matter — the application itself
can't tell you the difference, and no amount of clicking here will help.

Times shown here — including **Last Run At** on a periodic task — are in
{{ config.TIME_ZONE }}, and schedules are evaluated against that same clock, so a
job set for `02:15` runs at quarter past two by a local clock all year round.

## Symptoms that come back to a job

| Symptom | Job |
|---|---|
| Expired content is still playing | Clean up content |
| Content with a start date never appears | Update playlists |
| Room displays are showing yesterday's bookings | Pull room bookings |
| New rooms in the tenant never appear | Sync O365 rooms |
| Old schedule rules are piling up | Clean up schedule rules |
| No screen ever shows "needs attention" | Check screens |
| A screen's status history stops at some date | Check screens |

In each case check **Task Results** first. A failing job with a traceback tells
you far more than the symptom does.
