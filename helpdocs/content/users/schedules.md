# Scheduling what plays when

A **schedule** decides which playlist is playing at any given moment. Screens
point at a schedule, not at a playlist directly — which is what lets a display
change through the day or the week without anyone touching it.

## The default playlist

Every schedule has a **default playlist**. It plays whenever no rule matches.

If you only ever want one playlist on a screen, that's the whole job: create a
schedule, set its default playlist, and add no rules at all.

1. Go to **Schedules** and choose **Add schedule**.
2. Give it a **Name** and optionally a **Description**.
3. Choose the **Default playlist**.
4. Save.

![A schedule and its rules](screenshot:schedule-form)

## Adding a rule

A rule says "show *this playlist* on *these days* between *these times*".

1. Open the schedule and find the **Schedule rules** section.
2. Choose the **Playlist** the rule should show.
3. Set **Starts** — the date the rule becomes active. Use today's date for
   something that should work immediately, or a future date to set it up in
   advance.
4. Set **Occurrences** — which days it applies to, as a repeating pattern
   (for example, every Monday and Wednesday).
5. Set **Start time** and **End time**.
6. Set a **Priority** — see below.
7. Save.

![Setting up a schedule rule](screenshot:schedule-rule)

### End time and midnight

Set **End time** to `00:00` to mean *the end of the day*. Without that
convention, a rule ending at midnight would end immediately at the start of the
day instead.

For a rule that should run all day, use `00:00` to `00:00`.

## Priority: lowest number wins

When two or more rules match the same moment, the one with the **lowest priority
number** is used. Think of it as "priority 1 is first in the queue", not "bigger
is more important".

A worked example:

| Rule | Playlist | When | Priority |
|---|---|---|---|
| Term time | *Term Time* | Weekdays, 08:00–18:00 | 20 |
| Open Day | *Open Day* | Saturday 14 June, all day | 10 |

On a normal weekday, only the first rule matches, so *Term Time* plays. On Open
Day both could match, and *Open Day* wins because 10 is lower than 20.

!!! tip
    Leave gaps between your priority numbers — 10, 20, 30 rather than 1, 2, 3.
    That way you can slot something in later without renumbering everything.

## When nothing matches

If no rule applies right now, the **default playlist** plays. There is never a
moment with nothing to show, as long as the default playlist has content in it.

## Housekeeping

Rules whose repeating pattern has finished for good are tidied away
automatically, so a schedule doesn't accumulate years of dead entries. Rules that
recur indefinitely are never removed.

{% if perms.screens.delete_schedule %}
## Deleting a schedule

From the **Schedules** list, tick it, choose **Delete selected schedules**, and
confirm.

A schedule that a screen is using can't be deleted — point that screen at a
different schedule first.
{% endif %}
