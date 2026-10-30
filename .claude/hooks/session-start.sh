#!/usr/bin/env bash
set -euo pipefail

project_root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
# The tasker variant that just install recorded in .agents/stack.json: git (the default) or gitwt.
tasker_mode="$(sed -n 's/.*"tasker"[[:space:]]*:[[:space:]]*"\([a-z]*\)".*/\1/p' "$project_root/.agents/stack.json" 2>/dev/null | head -1 || true)"

read -r -d '' CONTEXT <<'CONTEXT_EOF' || true
## Gest Workflow Reminder

Use the project-local `g*` skills for substantial work:

- `gtw`: route project work into Gest
- `gsp`: create/update specs
- `gpl`: plan tasks and iterations
- `gis`: create durable tasks
- `gim`: implement one concrete task
- `gor`: execute phased work, using GitButler sequentially or physical git worktrees for parallel writes
- `gfm`: format/lint/static checks
- `gte`: tests and smoke/integration checks
- `gdo`: docs audit
- `grv`: review current changes
- `gcm`: GitButler commit/push/PR checkpoint
- `gpr`: GitHub issue promotion decision
- `gpa`: GitHub PR acceptance review

Keep Gest commands serialized. Use task notes with Done and Verification before
completing non-trivial leaves. Apply tag classification and ast-grep dependency
impact checks from .agents/skills/gtw/references/tag_dependency_workflow.md.
CONTEXT_EOF

if [ "$tasker_mode" = gitwt ]; then
  CONTEXT="$CONTEXT

Tasker variant gitwt: do each write task in its own worktree. \`just worktree-new NAME\`
makes one in ../<repo>.worktrees/NAME and sets it up. Keep the main checkout on
its base branch."
else
  CONTEXT="$CONTEXT

Tasker variant git: work on a branch in the main checkout. For parallel write
work, \`just worktree-new NAME\` makes a worktree for each task."
fi
# Report the worktrees that are ready to prune. Nothing is removed here.
script="$project_root/.agents/skills/gtw/scripts/worktree.py"
if [ -f "$script" ] && command -v uv >/dev/null 2>&1; then
  ready="$(cd "$project_root" && uv run --no-project --quiet --no-python-downloads --python '>=3.9' python "$script" list --report 2>/dev/null || true)"
  if [ -n "$ready" ]; then
    CONTEXT="$CONTEXT

$ready Tell the user; remove them only when the user asks."
  fi
fi

escape_json() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/$/\\n/g' | tr -d '\n' | tr '\001-\037' ' '
}

printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}' \
  "$(escape_json "$CONTEXT")"
