#!/usr/bin/env bash
# Run the documented restack commands of a plain-git stack on scratch repositories, and check that each one
# moves the stack with no conflict. The stack is main <- A <- B <- C.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
fail() { echo "stack-rebase-lab: $*" >&2; exit 1; }

# The lab sets each config that a commit or a rebase reads, so the git config of the user cannot change it.
g() {
  git -C "$repo" -c user.name=lab -c user.email=lab@example.invalid -c commit.gpgsign=false \
    -c rebase.gpgSign=false -c core.hooksPath=/dev/null -c rebase.updateRefs=false -c rebase.autoStash=false "$@"
}

# stack NAME: a remote and a clone with the stack main <- A <- B <- C, each branch pushed.
stack() {
  git init -q --bare -b main "$work/$1.git"
  repo="$work/$1"
  git clone -q "$work/$1.git" "$repo" 2>/dev/null
  g switch -qc main
  echo base > "$repo/base.txt"; g add base.txt; g commit -qm base
  g switch -qc A; echo a1 > "$repo/a.txt"; g add a.txt; g commit -qm A1
  echo a2 >> "$repo/a.txt"; g commit -qam A2
  g switch -qc B; echo b1 > "$repo/b.txt"; g add b.txt; g commit -qm B1
  g switch -qc C; echo c1 > "$repo/c.txt"; g add c.txt; g commit -qm C1
  g push -q origin main A B C 2>/dev/null
}

# check_stack BASE: A or BASE is below B, B is below C, and each file holds what the stack wrote.
check_stack() {
  [ "$(g rev-parse B~1)" = "$(g rev-parse "$1")" ] || fail "$2: B does not start at $1"
  [ "$(g rev-parse C~1)" = "$(g rev-parse B)" ] || fail "$2: C does not start at B"
  [ "$(g show C:b.txt)" = b1 ] && [ "$(g show C:c.txt)" = c1 ] || fail "$2: C lost a change of the stack"
}

# restack ARGS: run the documented restack on C, and check that it leaves A where it is.
restack() {
  local a_before
  a_before="$(g rev-parse A)"
  g switch -q C
  g rebase -q --update-refs "$@" > "$work/rebase.log" 2>&1 || { cat "$work/rebase.log" >&2; return 1; }
  [ "$(g rev-parse A)" = "$a_before" ] || fail "the restack moved the lower branch A"
}

# 1. A is amended. The documented form replays only B and C.
stack amend
g switch -q A; printf 'a1 amended\na2\n' > "$repo/a.txt"; g commit -q --amend -am "A2 amended"
restack --onto A 'A@{1}' || fail "the documented restack after an amend conflicts"
check_stack A "after an amend"
[ "$(g show C:a.txt)" = "$(printf 'a1 amended\na2')" ] || fail "after an amend: C does not have the amended A"

# 1b. A is amended twice. A@{1} is then the first amend, so the documented form saves the old tip first.
stack amend-twice
old_tip="$(g rev-parse A)"
g switch -q A; printf 'a1 once\na2\n' > "$repo/a.txt"; g commit -q --amend -am "A2 once"
printf 'a1 twice\na2\n' > "$repo/a.txt"; g commit -q --amend -am "A2 twice"
restack --onto A "$old_tip" || fail "the documented restack with a saved tip conflicts after two amends"
check_stack A "after two amends"

# The old form replays the old commit of A, so it must conflict. If it does not, the lab tests nothing.
stack amend-old
g switch -q A; printf 'a1 amended\na2\n' > "$repo/a.txt"; g commit -q --amend -am "A2 amended"
g switch -q C
if g rebase -q --update-refs A > /dev/null 2>&1; then fail "the lab expects the restack without --onto to conflict after an amend"; fi
g rebase --abort

# 2. A gains a commit. The documented form works here too.
stack grow
g switch -q A; echo a2 > "$repo/a2.txt"; g add a2.txt; g commit -qm A2
restack --onto A 'A@{1}' || fail "the documented restack after a new commit conflicts"
check_stack A "after a new commit"

# 3. A merges into main by squash. The form after a merge replays only B and C onto the new base.
stack squash
old_tip="$(g rev-parse A)"
g switch -q main; g merge -q --squash A > /dev/null; g commit -qm "A (squash)"; g push -q origin main 2>/dev/null
g fetch -q origin
restack --onto origin/main "$old_tip" || fail "the documented restack after a squash merge conflicts"
check_stack origin/main "after a squash merge"

# The old form after a squash merge replays the two commits of A onto the squash, so it must conflict.
stack squash-old
g switch -q main; g merge -q --squash A > /dev/null; g commit -qm "A (squash)"; g push -q origin main 2>/dev/null
g fetch -q origin
g switch -q C
if g rebase -q --update-refs origin/main > /dev/null 2>&1; then
  fail "the lab expects the restack without --onto to conflict after a squash merge"
fi
g rebase --abort

# The docs and the skills must give only the --onto form. A line that runs the rebase and has no --onto is a bare
# restack, also when the command wraps to the next line. The scripts hold the bare form on purpose, as samples.
bare="$(git -C "$repo_root" grep -nE 'rebase[^`]*--update-refs' -- ':!docs/specs/' ':!notes/' ':!scripts/' \
  | grep -v -- '--onto')" || [ $? -eq 1 ] || exit 1
[ -z "$bare" ] || { printf '%s\n' "$bare" >&2; fail "a doc gives a restack without --onto"; }

echo "stack-rebase-lab: amend, new commit and squash merge restack with no conflict"
