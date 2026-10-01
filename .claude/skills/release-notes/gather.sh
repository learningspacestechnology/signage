#!/usr/bin/env bash
# Prints the raw material for release notes: everything the working tree changes
# relative to the point where this branch left the base branch. Committed work,
# uncommitted edits and untracked files all count.
#
# Read-only apart from a `git fetch` of the base branch.
#
# Usage: gather.sh [base-branch]    (default: master)
set -uo pipefail

base_branch="${1:-master}"
cd "$(git rev-parse --show-toplevel)" || exit 1
deploy_dir="${SIGNAGE_DEPLOY_DIR:-$HOME/signage_deploy}"
# Screenshots and the lockfile are noise at this level; the help-doc and
# pyproject diffs say the same things in words.
noise=(':(exclude)*.png' ':(exclude)*.jpg' ':(exclude)*.jpeg' ':(exclude)*.gif'
       ':(exclude)*.webp' ':(exclude)uv.lock' ':(exclude)release-notes.md')

section() { printf '\n== %s ==\n' "$1"; }
# Passes stdin through, or prints "(none)" so an empty list can't be misread.
or_none() { local out; out="$(cat)"; if [ -n "$out" ]; then printf '%s\n' "$out"; else echo "${1:-}(none)"; fi; }

# Compare with the base as it stands on its remote, since that is what the PR
# merges into; fall back to the local branch if it can't be fetched.
remote="$(git config "branch.${base_branch}.remote" 2>/dev/null || true)"
base_ref="$base_branch"
if [ -n "$remote" ] && [ "$remote" != "." ]; then
    if git fetch --quiet "$remote" "$base_branch" 2>/dev/null; then
        base_ref="$remote/$base_branch"
    else
        echo "WARNING: could not fetch $remote/$base_branch; using local $base_branch, which may be stale."
    fi
fi
if ! git rev-parse --verify --quiet "${base_ref}^{commit}" >/dev/null; then
    echo "ERROR: no branch '$base_ref' to compare with."
    exit 1
fi

# The merge base, not the base tip: a two-point diff against the tip would also
# show, reversed, everything the base gained since this branch left it.
mb="$(git merge-base "$base_ref" HEAD)"

section "Comparison"
echo "Current branch: $(git branch --show-current) at $(git rev-parse --short HEAD)"
echo "Base:           $base_ref at $(git rev-parse --short "$base_ref")"
echo "Merge base:     $(git rev-parse --short "$mb")  <- all diffs below start here"
[ "$(git branch --show-current)" = "$base_branch" ] &&
    echo "WARNING: you are on $base_branch itself; there is nothing to compare."

section "Commits on this branch, not on $base_ref (merges omitted)"
git log --no-merges --format='%h %cs %s' "$mb..HEAD" | or_none

section "Uncommitted changes to tracked files"
git status --short --untracked-files=no | or_none

section "Untracked files (count as part of the release, but only ship if committed)"
git ls-files --others --exclude-standard | grep -vx 'release-notes.md' | or_none

section "Changed tracked files, merge base -> working tree (images, uv.lock excluded)"
git diff --stat=200 --stat-count=500 "$mb" -- "${noise[@]}"
images="$(git diff --name-only "$mb" -- '*.png' '*.jpg' '*.jpeg' '*.gif' '*.webp' | wc -l)"
echo "Plus $images changed image file(s)."

section "Submodules"
submodules="$(git config -f .gitmodules --get-regexp '^submodule\..*\.path$' 2>/dev/null | awk '{print $2}')"
[ -z "$submodules" ] && echo "(none)"
for path in $submodules; do
    old="$(git ls-tree "$mb" -- "$path" | awk '{print $3}')"
    # Without its own .git, `git -C` would silently run against this repo.
    if [ ! -e "$path/.git" ]; then echo "$path: not checked out"; continue; fi
    new="$(git -C "$path" rev-parse HEAD)"
    if [ -z "$old" ]; then echo "$path: submodule added in this release"; continue; fi
    if [ "$old" = "$new" ]; then echo "$path: unchanged"; continue; fi
    echo "$path: ${old:0:7} -> ${new:0:7}"
    echo "  Commits gained:"
    git -C "$path" log --no-merges --format='    %h %cs %s' "$old..$new" 2>&1 | or_none '    '
    echo "  Commits dropped (pointer moved backwards over these):"
    git -C "$path" log --no-merges --format='    %h %cs %s' "$new..$old" 2>&1 | or_none '    '
    echo "  Net file change (none = no real change, whatever the commits say):"
    git -C "$path" diff --stat "$old" "$new" 2>&1 | sed 's/^/    /' | or_none '    '
    echo "  New migrations:"
    git -C "$path" diff --name-only --diff-filter=A "$old" "$new" 2>/dev/null |
        grep -E '/migrations/[0-9]{4}_.*\.py$' | sed 's/^/    /' | or_none '    '
    dirty="$(git -C "$path" status --short)"
    [ -n "$dirty" ] && printf '  Uncommitted inside the submodule:\n%s\n' "$(sed 's/^/    /' <<<"$dirty")"
done

section "New migrations (run automatically on container start)"
{ git diff --name-only --diff-filter=A "$mb"; git ls-files --others --exclude-standard; } |
    grep -E '/migrations/[0-9]{4}_.*\.py$' | sort -u | or_none

section "Settings: base_settings.py and settings.sample.py"
git diff "$mb" -- advertising/base_settings.py advertising/settings.sample.py | or_none

section "New settings vs the deploy repo ($deploy_dir)"
added="$(git diff -U0 "$mb" -- advertising/base_settings.py |
    sed -nE 's/^\+([A-Z][A-Z0-9_]*)[[:space:]]*=.*/\1/p' | sort -u)"
if [ -z "$added" ]; then
    echo "(no new top-level settings)"
elif [ ! -d "$deploy_dir" ]; then
    echo "Deploy repo not found; cannot check. New settings: $(echo $added)"
else
    for name in $added; do
        s=no; e=no
        grep -qw "$name" "$deploy_dir/docker/advertising/settings.py" 2>/dev/null && s=yes
        grep -qw "$name" "$deploy_dir/.env.sample" 2>/dev/null && e=yes
        echo "$name: read by deploy settings.py=$s, in .env.sample=$e"
    done
fi

section "Dependencies (pyproject.toml)"
git diff "$mb" -- pyproject.toml | or_none

section "KNOWN_ISSUES.md (a removed entry is a fix)"
git diff "$mb" -- KNOWN_ISSUES.md | or_none

section "Help docs (the best map of user-facing change; read these diffs)"
{ git diff --stat=200 "$mb" -- helpdocs/content
  git ls-files --others --exclude-standard -- helpdocs/content | sed 's/^/new page: /'; } | or_none
