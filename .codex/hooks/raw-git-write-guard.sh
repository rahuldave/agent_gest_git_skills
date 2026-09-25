#!/usr/bin/env bash
set -euo pipefail

input="$(cat)"
command_text="$(printf '%s' "$input" | sed -n 's/.*"tool_input"[^{]*{[^}]*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p; s/.*"cmd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p; s/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"

# Mode is selected by the execution environment or a leading command assignment.
# Text later in a command (for example an echo) cannot change the guard mode.
execution="${GEST_VCS_EXECUTION:-}"
checked_command="$command_text"
if [[ "$command_text" =~ ^[[:space:]]*(env[[:space:]]+)?GEST_VCS_EXECUTION=(git-worktrees|gitbutler-workspace)[[:space:]]+ ]]; then
  [ -n "$execution" ] || execution="${BASH_REMATCH[2]}"
  checked_command="${command_text:${#BASH_REMATCH[0]}}"
fi
if [ "$execution" = git-worktrees ]; then
  exit 0
fi

branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
if [ "$execution" != gitbutler-workspace ] && [ "$branch" != gitbutler/workspace ]; then
  exit 0
fi

if printf '%s' "$checked_command" | grep -Eq '(^|[;&|][[:space:]]*)git[[:space:]]+(-C[[:space:]]+[^[:space:]]+[[:space:]]+)?(commit|add|restore|reset|checkout|switch|branch|worktree|merge|rebase|cherry-pick|revert|pull|push|clean|rm|mv|tag)([[:space:]]|$)'; then
  cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Raw git write command blocked in the GitButler workspace. Use but commands while GitButler owns this workspace, or select explicit physical git-worktree execution mode."}}
JSON
fi
