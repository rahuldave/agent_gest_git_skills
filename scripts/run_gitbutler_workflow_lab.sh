#!/usr/bin/env bash
set -euo pipefail

command -v but >/dev/null || { echo 'GitButler CLI (but) is required' >&2; exit 1; }
command -v git >/dev/null || { echo 'git is required' >&2; exit 1; }

# mktemp owns every path removed by this lab; never remove a caller-supplied path.
lab_root="$(mktemp -d "${TMPDIR:-/tmp}/agent-gest-gitbutler.XXXXXXXX")"
cleanup() {
  status=$?
  trap - EXIT
  for repo in "$lab_root"/main/repo "$lab_root"/integration/repo; do
    if [ -d "$repo/.git" ]; then
      git -C "$repo" worktree remove --force "$lab_root/$(basename "$(dirname "$repo")")/worktree-a" >/dev/null 2>&1 || true
      git -C "$repo" worktree remove --force "$lab_root/$(basename "$(dirname "$repo")")/worktree-b" >/dev/null 2>&1 || true
    fi
  done
  rm -rf -- "$lab_root"
  exit "$status"
}
trap cleanup EXIT

fail() { echo "GitButler workflow lab: $*" >&2; exit 1; }

run_base() (
  label="$1"
  case "$label" in
    main) base=main ;;
    integration) base=integration ;;
    *) fail "unknown base $label" ;;
  esac
  lab="$lab_root/$label"
  repo="$lab/repo"
  remote="$lab/remote.git"
  mkdir -p "$repo"
  git init --bare --initial-branch=main "$remote" >/dev/null
  cd "$repo"
  git init -b main >/dev/null
  git config user.name workflow-test
  git config user.email workflow-test@example.invalid
  git remote add origin "$remote"
  printf '# Workflow lab\n' > README.md
  mkdir src
  printf 'base\n' > src/app.txt
  git add README.md src/app.txt
  git commit -m 'chore: initialize workflow lab' >/dev/null
  git push -u origin main >/dev/null

  if [ "$base" = integration ]; then
    git switch -c integration >/dev/null
    printf 'persistent integration baseline\n' > integration.txt
    git add integration.txt
    git commit -m 'chore: initialize persistent integration branch' >/dev/null
    git push -u origin integration >/dev/null
    git switch integration >/dev/null
  fi
  base_oid="$(git rev-parse "origin/$base")"
  main_oid="$(git rev-parse origin/main)"
  [ "$base" = main ] || [ "$base_oid" != "$main_oid" ] || fail 'integration must differ from main'

  but setup >/dev/null
  if [ "$base" = integration ]; then
    but unapply integration >/dev/null
  fi
  but config target "origin/$base" >/dev/null
  but pull >/dev/null
  target_state="$(but config target)"
  printf '%s\n' "$target_state" | grep -F "origin/$base" >/dev/null || fail "target is not origin/$base"
  printf '%s\n' "$target_state" | grep -F "$base_oid" >/dev/null || fail "target has stale base commit"

  printf 'plain branch change\n' > plain.txt
  but branch new demo/plain >/dev/null
  but commit demo/plain -m 'test: add plain change' >/dev/null
  but push demo/plain >/dev/null

  but branch new demo/multi >/dev/null
  printf 'session edit one\n' > session.txt
  but commit demo/multi -m 'test: first session edit' >/dev/null
  printf 'session edit two\n' >> session.txt
  but commit demo/multi -m 'test: second session edit' >/dev/null
  but push demo/multi >/dev/null

  but branch new demo/stack-base >/dev/null
  printf 'stack base\n' > stack.txt
  but commit demo/stack-base -m 'test: add stack base' >/dev/null
  but branch new --anchor demo/stack-base demo/stack-child >/dev/null
  printf 'stack child\n' >> stack.txt
  but commit demo/stack-child -m 'test: add stack child' >/dev/null
  but push demo/stack-base >/dev/null
  but push demo/stack-child >/dev/null

  for branch in demo/plain demo/multi demo/stack-base demo/stack-child; do
    git ls-remote --exit-code --heads origin "$branch" >/dev/null || fail "missing pushed $branch"
    git fetch -q origin "$branch" || fail "cannot fetch $branch"
    head="$(git rev-parse FETCH_HEAD)"
    git merge-base --is-ancestor "$base_oid" "$head" || fail "$branch does not contain selected base"
    [ "$(git merge-base "$base_oid" "$head")" = "$base_oid" ] || fail "$branch forked before selected base"
    if [ "$base" = integration ]; then
      git merge-base --is-ancestor "$main_oid" "$head" || fail "$branch lost main history"
    fi
  done
  multi_head="$(git ls-remote origin refs/heads/demo/multi | cut -f1)"
  [ "$(git rev-list --count "$base_oid..$multi_head")" -ge 2 ] || fail 'multi branch lost a commit'
  stack_parent="$(git ls-remote origin refs/heads/demo/stack-base | cut -f1)"
  stack_child="$(git ls-remote origin refs/heads/demo/stack-child | cut -f1)"
  git merge-base --is-ancestor "$stack_parent" "$stack_child" || fail 'stack child does not contain parent'
  [ "$(git rev-list --count "$base_oid..$stack_child")" -ge 2 ] || fail 'stack child has too few commits'
  [ "$(git rev-parse "origin/$base")" = "$base_oid" ] || fail 'selected base moved during GitButler operations'

  but teardown >/dev/null 2>&1 || true
  git switch "$base" >/dev/null
  for suffix in a b; do
    git worktree add -b "demo/worktree-$suffix" "$lab/worktree-$suffix" "$base" >/dev/null
    (
      cd "$lab/worktree-$suffix"
      printf 'isolated worktree %s\n' "$suffix" > "worktree-$suffix.txt"
      git add "worktree-$suffix.txt"
      git commit -m "test: add worktree $suffix change" >/dev/null
      git push -u origin "demo/worktree-$suffix" >/dev/null
    )
    git worktree remove "$lab/worktree-$suffix" >/dev/null
    worktree_head="$(git ls-remote origin "refs/heads/demo/worktree-$suffix" | cut -f1)"
    [ "$(git rev-parse "$worktree_head^")" = "$base_oid" ] || fail "worktree $suffix did not fork selected base"
  done
  [ "$(git rev-parse "origin/$base")" = "$base_oid" ] || fail 'selected base changed after worktree flow'
  echo "GitButler workflow lab passed with $base as selected base"
)

run_base main
run_base integration
