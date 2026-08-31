# Screen reachability checks

The heartbeat tells you whether a display's *player* is running. It cannot tell
you whether the *device* is alive, because a switched-off screen and one with a
crashed browser both simply stop polling.

Reachability checking closes that gap: the system pings screens that have
stopped reporting, and the answer separates the two. This page covers what it
needs in order to work, what it deliberately does not do, and how to tell it
apart from a genuine outage.

Read [What display devices call](help:player-api) first if you haven't — the
heartbeat is the other half of the picture.

## The three states

| State | Condition | Reading |
|---|---|---|
| **Online** | Polled within the last {{ config.SCREEN_OFFLINE_AFTER }} | Nothing to do |
| **Needs attention** | Not polling, but answers ping | The device is up, its software isn't |
| **Needs attention** | Stopped polling under {{ config.SCREEN_ATTENTION_AFTER }} ago | Probably a blip; look again |
| **Offline** | Everything else | Power, network, or the wrong IP registered |

The two amber cases share a colour but not a meaning, so the reason is always
shown next to it — in the **Detail** column on the screens list, and on the
dashboard watchlist. Never diagnose from the colour alone.

**Ping outranks the grace window.** A screen that both answers ping and stopped
reporting two minutes ago is reported as "responds to ping", because that is the
more useful of the two facts.

A successful ping keeps a screen amber for {{ config.SCREEN_PING_WINDOW }} —
deliberately longer than the {{ config.SCREEN_CHECK_SCHEDULE }} check interval,
so a single missed probe cannot flip a healthy-but-silent screen to red.

## What it needs to work

Reachability checking is **off by default** and has three prerequisites. All
three are deployment matters — ask whoever administers the system rather than
trying to change them from here.

1. **The setting must be on.**
{% if config.SCREEN_PROBE_ENABLED %}   It is on for this deployment.
{% else %}   It is **off** for this deployment, so no screen will ever show
   "responds to ping", and every failing display reads as offline.
{% endif %}
2. **`ping` must be present in the worker's image.** It is not part of the base
   Python image and has to be installed explicitly. When it is missing the
   worker logs a warning once per cycle naming the package, and records nothing
   — see [Telling the failure modes apart](#telling-the-failure-modes-apart).
3. **The worker must be able to route to the screens.** The check runs from the
   worker container, not from the machine you are sitting at, so displays see
   the probe arriving from the server's own address. Two things break this: a
   firewall between the server and the display network, and a screen subnet that
   overlaps the container network's own address range, in which case the traffic
   never leaves the host at all.

## What it deliberately doesn't do

- **It never writes `last seen`.** The two signals are stored separately and
  combined only when the status is worked out. A ping cannot make a screen look
  like it is reporting when it isn't.
- **It only probes screens that aren't reporting.** A screen that is polling has
  already answered the more useful question, so probing it would be traffic for
  nothing.
- **It never restarts a display.** A screen whose rotation is running is left
  alone entirely; the check writes only the two reachability timestamps.
- **It doesn't retry.** One echo request per screen per cycle, with a short
  timeout. That is why the window a good ping counts for is much longer than the
  interval — the tolerance for a lost packet is in the window, not in retries.

## Telling the failure modes apart

The two offline reasons look similar and mean opposite things:

| Reason | Meaning |
|---|---|
| **No contact and no ping response** | The system asked. Nothing came back. Probing is working; the device really is unreachable. |
| **No contact** | Nothing asked. Says nothing about the device. |

So an estate where *every* screen says plain "no contact" and none say "needs
attention" is telling you about the checker, not the screens — one of the three
prerequisites above isn't met. Check **Task Results** for the **Check screens**
job and read the worker's log for the warning about `ping`.

!!! note "Not-probed is not the same as failed"
    When `ping` is missing the check writes nothing at all, rather than
    recording a failed probe. That's on purpose: recording it would turn a
    deployment gap into a fleet-wide fault report, and you would go looking for
    a network problem that doesn't exist.

## Status history

Every status change is recorded — what it changed to, why, and when. Open a
screen and look under **Status**.

This is what answers "how long has it been like that", and it is the only place
flapping is visible: a screen alternating every few cycles is a different fault
from one that failed once, and the live status looks identical for both.

Two things worth knowing:

- **History is written by the same job that does the probing**, so it is at most
  one cycle behind. The status shown is always worked out live, never read back
  from history — where the interface shows "since", it does so only while the
  two agree, and falls back to the last check-in otherwise.
- **Rows are kept for {{ config.SCREEN_HISTORY_DAYS }} days**, except that each
  screen's most recent change is never deleted. A screen dark for six months
  still tells you when it went dark.

## Related

- [What display devices call](help:player-api) — the heartbeat, and what
  actually sets `last seen`.
- [Background jobs](help:scheduled-tasks) — the **Check screens** job, its
  schedule, and what turning it off costs.
- [Commissioning a display](help:device-commissioning) — getting a new screen
  registered in the first place.
- [Managing screens](help:users/screens) — the same states, written for
  operators.
