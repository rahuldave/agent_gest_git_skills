#!/usr/bin/env bash
set -euo pipefail

input="$(cat)"
command_text="$(printf '%s' "$input" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"

# Mode is selected by the execution environment or a leading command assignment.
# Text later in a command (for example an echo) cannot change the guard mode.
execution="${GEST_VCS_EXECUTION:-}"
checked_command="$command_text"
if [[ "$command_text" =~ ^[[:space:]]*(env[[:space:]]+)?GEST_VCS_EXECUTION=(git-worktrees|gitbutler-workspace)[[:space:]]+ ]]; then
  [ -n "$execution" ] || execution="${BASH_REMATCH[2]}"
  checked_command="${command_text:${#BASH_REMATCH[0]}}"
fi
# The tasker variant that just install recorded in .agents/stack.json: git (the default) or gitwt.
project_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
tasker_mode="$(sed -n 's/.*"tasker"[[:space:]]*:[[:space:]]*"\([a-z]*\)".*/\1/p' "$project_root/.agents/stack.json" 2>/dev/null | head -1 || true)"
# In the gitwt variant the main checkout stays on its base branch, so a commit there gets a warning. It is not blocked,
# and a block of the GitButler rules below comes first.
warning=""
git_options='(-[cC][[:space:]]+[^[:space:]]+[[:space:]]+)*'
if [ "$tasker_mode" = gitwt ] \
  && printf '%s' "$checked_command" | grep -Eq "(^|[;&|][[:space:]]*)git[[:space:]]+${git_options}commit([[:space:]]|\$)"; then
  # The checkout of the commit: the folder of git -C, else this folder.
  commit_dir="$(printf '%s' "$checked_command" | sed -nE "s/.*git[[:space:]]+(-c[[:space:]]+[^[:space:]]+[[:space:]]+)*-C[[:space:]]+([^[:space:]]+).*/\2/p" | head -1 || true)"
  git_dir="$(git -C "${commit_dir:-.}" rev-parse --path-format=absolute --git-dir 2>/dev/null || true)"
  common_dir="$(git -C "${commit_dir:-.}" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
  if [ -n "$git_dir" ] && [ "$git_dir" = "$common_dir" ]; then
    warning="This project uses the gitwt variant: commit in a worktree, and keep the main checkout on its base branch. just worktree-new NAME makes one."
  fi
fi
finish() {
  if [ -n "$warning" ]; then
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"%s"}}\n' "$warning"
  fi
  exit 0
}
if [ "$execution" = git-worktrees ]; then
  finish
fi

branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
if [ "$execution" != gitbutler-workspace ] && [ "$branch" != gitbutler/workspace ]; then
  finish
fi

if printf '%s' "$checked_command" | grep -Eq '(^|[;&|][[:space:]]*)git[[:space:]]+(-C[[:space:]]+[^[:space:]]+[[:space:]]+)?(commit|add|restore|reset|checkout|switch|branch|worktree|merge|rebase|cherry-pick|revert|pull|push|clean|rm|mv|tag)([[:space:]]|$)'; then
  cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Raw git write command blocked in the GitButler workspace. Use but commands while GitButler owns this workspace, or select explicit physical git-worktree execution mode."}}
JSON
  exit 0
fi
finish
