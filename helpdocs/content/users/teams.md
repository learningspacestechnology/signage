# Teams and what you can see

A **team** decides which content, playlists, schedules and screens you can see
and edit. It is the main reason something you expect to find isn't in a list.

## What a team covers

Every piece of content, every playlist, every schedule and every screen belongs
to at least one team. When you look at any list in
{{ config.ADMIN_SITE_NAME }}, you are only shown the ones belonging to the team
you are currently working in.

The dashboard counts work the same way: they are counts *for your current team*,
not for the whole system.

## Your locations

Screens have a second limit. An administrator may give you access to particular
**locations** — some campuses, buildings or rooms — rather than the whole
estate. If so, you see only the screens in those places, and only those places
in the building and room lists.

The two limits add up: you see a screen only if it is in your current team
**and** in one of your locations. Content, playlists and schedules aren't tied to
a place, so locations don't affect them.

Three things follow if your account is limited to locations:

- A screen must have a **Building**, and a **Room** too unless you have
  access to the whole building. A screen outside your locations would disappear
  from your list as soon as you saved it, so the form won't let you leave
  them blank.
- The **Building** and **Room** boxes on a screen offer only your places.
- If you have no locations at all, the dashboard says so and your screen list is
  empty. Ask an administrator to add you to a location group.

## Your current team

The team you're working in is shown at the top of every page.

![The team indicator and switcher in the page header](screenshot:team-switcher)

If you belong to more than one team, click it to switch:

1. Click the team name at the top of the page.
2. Choose the team you want from the list.
3. The page reloads, and every list now shows that team's items.

Your choice sticks until you change it again, including next time you sign in.

!!! note "Administrators see an extra option"
    Accounts with full administrator rights also get an **All teams** entry,
    which shows everything from every team at once. If you don't have it, you're
    not missing anything — it exists so administrators can support other teams.

## What happens when you create something

Anything you create is automatically put into the team you're currently working
in. You don't have to choose, and you can't accidentally file it under someone
else's team.

If you need something to be shared between two teams, ask an administrator —
only administrators can put one item into several teams at once.

## Items shared with another team

An administrator can put one item into two teams so both can work on it. A shared
schedule might use the other team's playlist as its default; a shared playlist
might inherit from theirs or hold their content.

Where that happens, the choice is shown with the owning team in brackets, and the
field says so underneath:

```
Christmas message (another team: Library)
```

Leave it as it is and the rest of the form saves normally — you don't have to
touch it to edit the name, the times, or anything else. What you can't do is pick
something *different* of theirs: only the item already in use is offered, and the
rest of their content stays out of the list.

!!! warning "Changing one of these changes their screens too"
    A choice marked with another team's name is in use on that team's screens.
    Replace it with one of your own — or untick it — and their displays change
    straight away, without them being told. Check with them first.

## Common questions

**A colleague made a playlist and I can't see it.**
They were probably working in a different team. Ask which team it belongs to, and
whether you should be a member of it.

**I switched teams and my screens vanished.**
They belong to the other team. Switch back using the team name at the top of the
page.

**A choice in a form is marked "another team".**
The item belongs to a team you're not working in, and it's offered only because
this shared item already uses it. Leave it alone unless you've agreed the change
with that team — see *Items shared with another team* above.

**I can see a building but not all of its rooms.**
You have been given particular rooms in it rather than the whole building. Ask
an administrator if you need the rest.

**I'm only in one team and a screen is still missing.**
It may be in a room outside your locations — see *Your locations* above.
Otherwise, see [Something isn't showing on a screen](help:troubleshooting).

**I need access to another team.**
Ask an administrator to add you. Being in two teams means you can switch between
them; it doesn't merge them into one view.
