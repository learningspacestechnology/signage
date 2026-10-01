---
name: release-notes
description: Write release-notes.md, a short user-centric summary of everything the current branch changes relative to master (new features, improvements, bug fixes, breaking changes and actions needed), ready to paste into the team's Teams channel. Use before merging dev into master, or whenever the user asks for release notes, a changelog, a "what's new" post or a summary of what's about to ship.
argument-hint: "[base-branch]"
allowed-tools: Read, Grep, Glob, Write, Bash(bash .claude/skills/release-notes/gather.sh*), Bash(git diff *), Bash(git log *), Bash(git show *), Bash(git status *), Bash(git ls-files *), Bash(git -C room_schedules log *), Bash(git -C room_schedules diff *), Bash(git -C room_schedules show *)
---

# Release notes

Write `release-notes.md` at the repo root: a brief post for the team's Teams
channel saying what is about to land on master. The readers are the people who
**use and run** the signage system (content editors, schedulers, admins, the
odd technical person), not the developers who wrote it. They will skim it in a
chat feed, so the notes should be short, but anything that needs them to act
must still be in there.

Base branch: `$ARGUMENTS` if given, otherwise `master`.

## 1. Gather the facts

```bash
bash .claude/skills/release-notes/gather.sh [base-branch]
```

This compares the **merge base** with the **working tree**, so committed work on
this branch, uncommitted edits and untracked files all count. It prints commits,
changed and untracked files, submodule movement, new migrations, the settings
diff with a check against the deploy repo, dependency changes, `KNOWN_ISSUES.md`
changes, and which help pages changed.

It uses the merge base because master carries PR merge commits that dev does not
have. A plain diff against master's tip would show those as changes this branch
reverts. It uses the working tree because the user runs this just before
merging and wants the codebase as it stands. Uncommitted work only ships if it
is committed, though, so note which items come *only* from uncommitted or
untracked files. You'll report them at the end.

## 2. Work out what changed, from the code

Treat commit messages as hints, not evidence. Many here say no more than
"chore: update subproject commit reference", and much of a release may not be
committed yet. Establish each change from the diff (`git diff <merge-base> -- <path>`,
or read untracked files directly). In rough order of payoff:

1. **Help docs**: `helpdocs/content/`. This project updates the matching help
   page in the same change as any user-facing behaviour, so this diff is the
   closest thing to a ready-made list of what users will notice, already in
   their words. A new page usually means a new feature, and its title is what
   to point readers at.
2. **`KNOWN_ISSUES.md`**: a removed entry is a bug fix, with its symptom
   already written up.
3. **Admin, views, templates, URLs and the sidebar** (`UNFOLD` in
   `advertising/base_settings.py`): what appears on screen and what it is
   called. Take labels from here so the notes use the words people see.
4. **Migrations and models**: new things users can set. A migration that
   drops a field or model deletes data, so treat it as breaking.
5. **Tests**: for a fix, a new test's name and docstring often state the bug
   more precisely than the commit does.
6. **Submodule (`room_schedules`)**: the gather output lists commits gained and
   dropped and the net file change. If a pointer moved but no files changed
   (for example a rewind across merge commits), nothing changed.
7. **`CLAUDE.md`**: its diff often explains in one paragraph why a new
   feature exists.

For a large new app, don't read every file. Its help page, models, admin and
`CLAUDE.md` section say what it is for.

Leave out anything a user would not notice: tests on their own, refactors, dev
tooling (including `.claude/`), screenshot re-captures, `CLAUDE.md` itself,
small doc wording edits, and scratch files at the repo root (API specs, notes)
that are not part of the app.

## 3. Sort each change

**Action needed** covers anything someone must *do*, or anything that stops
working the way it did. Check each of these:

- A new setting that production must set, such as an API key. The gather
  output shows whether the deploy repo already reads it. If it doesn't, the
  feature cannot be configured in production yet, so tell the user in the
  terminal. The post itself should only say what has to be set, and who sets it.
- Permissions that must be granted before a new feature is usable, particularly
  one required *alongside* an existing permission. Without it, users see an
  empty page or picker and nothing explains why.
- Removed or renamed features, sidebar entries, fields or URLs that people use.
- Changes to what the displays fetch (the player API, `/meta`, room-display
  URLs), because screens in the field depend on these.
- A destructive migration.

These are **not** action items: routine migrations (the container runs `migrate`
on start), dependency bumps (the deploy rebuilds the image every time), and new
scheduled tasks that ship pre-configured in `CELERY_BEAT_SCHEDULE`. If one of
these changes what people see, describe it as a feature instead. For example,
"room details refresh nightly from the Learning Spaces Datastore".

Sort everything else into:

- **New**: something users could not do before.
- **Improved**: an existing feature that now works noticeably differently or
  better.
- **Fixed**: something that was wrong and now isn't. Only claim a fix when the
  diff shows the wrong behaviour went away: a removed known issue, a fix commit
  with matching code, or a regression test. A feature and the fixes made to it
  during the same release are one feature, not a feature plus fixes.

## 4. Write it

Use this shape. Drop any section that would be empty.

```markdown
# Signage update: <today's date, e.g. 3 March 2027>

One or two plain sentences giving the headline of this release.

## ⚠️ Action needed
- **Who does what**: what to do, and what happens if it isn't done.

## ✨ New
- **Short name**: what you can now do and where to find it. See *Help page title* in Help.

## 🔧 Improved
- **Short name**: what's different.

## 🐛 Fixed
- **Short name**: what used to go wrong, which no longer does.

Full details are in **Help & Tutorials** in the admin sidebar.
```

How to write the bullets:

- **Say what it means for the reader.** Write "Screens can now be linked to a
  real room, so you can filter the screen list by building", not "Added
  `Screen.room` FK to `estate.Room`".
- **Use the names people see** on screen: sidebar entries, page titles, button
  text, filter names. Leave out file paths, model or class names, functions,
  commit hashes and ticket numbers. The one exception is **Action needed**. A
  setting name such as `LSD_API_KEY` is exactly what the deployer must set, so
  it belongs there.
- **Use one bullet per change**, one or two sentences long, each led by a bold
  phrase. Fold related changes into one bullet. A new area of the admin is
  one bullet, not one per page.
- **Point to the help page** by its title when a feature has one. The help
  page holds the detail, so the note can stay short.
- **Keep it brief.** Aim for 150–350 words, and never go past about 450: once
  there, merge bullets or drop the least noticeable. Action-needed items are
  never the ones dropped.
- **Use only formatting that survives Teams:** headings, bold, italics, flat
  bullets and links. Tables, code blocks, nested lists and HTML paste into
  Teams badly.
- **Be plain and friendly.** Skip hype like "exciting", "powerful",
  "seamless" and "we're thrilled".

## 5. Check, write, report

Before writing, re-read the draft against the diff:

- Can you point at the code behind every bullet?
- Is anything claimed that isn't there, or described as bigger than it is?
- Is any action item missing?

Write `release-notes.md`, replacing any previous one. The file is per-release.

Then report in the terminal, **not** in the file:

- The path and the word count.
- **Items that exist only in uncommitted or untracked files.** List them by
  bullet. They will not ship unless committed, and the notes would then promise
  something master doesn't have.
- New settings the deploy repo does not read yet.
- Anything you left out that the user might want in, and anything you were
  unsure how to classify. The user knows the audience better than the diff
  does.
