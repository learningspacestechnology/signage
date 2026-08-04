# Settings with no screen

Some behaviour is fixed at deployment time and has no form anywhere in the
interface. When someone asks for one of these to change, it's a deployment
request — this page tells you what to ask for and what it will affect.

Values shown are what **this** deployment is currently running.

## Content and uploads

**Maximum image size** — currently
{{ config.MAX_IMG_WIDTH }} × {{ config.MAX_IMG_HEIGHT }}.
Images larger than this are rejected on upload. Raising it lets bigger files
through, at the cost of storage and of slower loads on modest display hardware.

Note that the help pages quote this limit from the live setting, so they stay
correct when it changes.

## Screens

**Site name** — currently "{{ config.ADMIN_SITE_NAME }}".
Appears on the sign-in page, the header of every page, and the sign-out page.

**Unconfigured screen message** — currently
"{{ config.UNCONFIGURED_SCREEN_MESSAGE }}".
Shown on the page an unregistered display gets. Worth customising to name the
team that should be contacted.

**Auto-create screens for new addresses** — currently
{% if config.AUTO_MAKE_SCREENS_FOR_NEW_IPS %}**on**{% else %}**off**{% endif %}.
When on, an unrecognised device gets a screen record created for it
automatically instead of the "not configured" page. Convenient for a large
rollout; the rest of the time it fills the screen list with entries nobody
recognises. Leave it off unless you're commissioning in bulk.

**IP access control** — currently
{% if config.IP_ACCESS_CONTROL_ENABLED %}**on**{% else %}**off**{% endif %}.
Turning it off makes every display URL public. See
[Commissioning a display](help:device-commissioning).

**Default display time** — the fallback duration for a playlist entry that sets
none and whose playlist sets none. In practice every playlist has a default
duration, so this rarely comes into play.

## Schedules

**Default schedule.** A schedule can be flagged as the system-wide default, used
by screens that have none assigned. **This flag is deliberately not editable in
the interface** — it is global rather than per-team, so exposing it would let one
team change what another team's screens fall back to. Changing it requires
database access; ask the deployment team, and be specific about which schedule.

## Room displays

**Day boundary** — the hour at which "today" is considered to start for room
schedules, so bookings running past midnight stay on the right day. The default
is 4am. Rarely changed.

**Content duration** — a per-room, per-building and per-group field that still
appears in some places but **is no longer used**. Ignore it. Page timing is
controlled by **pagination duration**, and booking changes reach the screen within
about ten seconds regardless. Setting it has no effect.

## Time zone

Currently **{{ config.TIME_ZONE }}**. Everything displayed — schedule rule times,
booking times, last-seen timestamps — is in this zone.

## Microsoft integration

The credentials for both the sign-in and the room-calendar registrations, the
redirect address, the domain allow-list, whether accounts are auto-created and
whether they're auto-granted staff status. All deployment-time only. See
[Microsoft sign-in](help:sso-and-entra).

## Background jobs

Job schedules **can** be changed in the interface, despite the defaults being set
in configuration — see [Background jobs](help:scheduled-tasks). If someone asks
for a job to run more often, you can usually do it yourself.
