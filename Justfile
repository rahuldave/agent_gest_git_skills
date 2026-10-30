setup:
  @echo "No repository-local dependencies to install. Ensure git, gest, just, uv, rsync, and optional gh, but, ast-grep, direnv, cx are available."

lint:
  scripts/check_repo.sh

static: lint

test:
  scripts/run_gitbutler_workflow_lab.sh
  scripts/run_tag_dependency_agent_dry_run.sh
  scripts/run_tag_dependency_typescript_lab.sh
  scripts/run_language_profile_labs.sh
  scripts/run_cx_examples_lab.sh
  scripts/run_agentic_target_lab.sh
  scripts/run_agent_result_lab.sh
  scripts/run_agent_task_draft_lab.sh

tag-dependency-dry-run:
  scripts/run_tag_dependency_agent_dry_run.sh

tag-dependency-live-lab:
  scripts/run_tag_dependency_typescript_lab.sh

language-profile-labs:
  scripts/run_language_profile_labs.sh

cx-examples-lab:
  scripts/run_cx_examples_lab.sh

agentic-target-lab:
  scripts/run_agentic_target_lab.sh

agent-result-lab:
  scripts/run_agent_result_lab.sh

agent-task-draft-lab:
  scripts/run_agent_task_draft_lab.sh

agent-result-recursive-live-lab TRANSCRIPT_DIR:
  scripts/run_agent_result_recursive_live_lab.sh "{{TRANSCRIPT_DIR}}"

protocol-flow-labs: agentic-target-lab agent-result-lab agent-task-draft-lab

workflow-lab:
  scripts/run_gitbutler_workflow_lab.sh

# Install this package into a scratch repository with the installer of a jnterfaces clone, and check the result
install-test:
  #!/usr/bin/env bash
  set -euo pipefail
  jnterfaces="${JNTERFACES_DIR:-$PWD/../jnterfaces}"
  target="$(mktemp -d)"; trap 'rm -rf -- "$target"' EXIT
  git -C "$target" init -q
  printf '{"model": "mine", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine.sh"}]}]}}\n' > "$target/x.json"
  mkdir -p "$target/.claude" && mv "$target/x.json" "$target/.claude/settings.json"
  install() { uv run --quiet --script "$jnterfaces/scripts/install_stack.py" --target "$target" --clone "agent_gest_git_skills=$PWD" "$@"; }
  install --defaults --without prose tasker
  fail() { echo "install-test: $*" >&2; exit 1; }
  for file in .agents/skills/gtw/SKILL.md .agents/skills/just/SKILL.md .claude/hooks/session-start.sh .codex/hooks/session-start.sh AGENTS.md .agents/gest-git-install.json; do
    test -f "$target/$file" || fail "missing $file after the install"
  done
  grep -q '"mine.sh"' "$target/.claude/settings.json" || fail "the install dropped the hook of the user"
  grep -q 'session-start' "$target/.claude/settings.json" || fail "the install merged no Claude hook"
  grep -q 'session-start' "$target/.codex/hooks.json" || fail "the install merged no Codex hook"
  test -f "$target/.agents/just/roles/agent_gest_git_skills.just" || fail "missing the role recipes after the install"
  [ "$(just --justfile "$target/Justfile" tasker-mode)" = git ] || fail "just tasker-mode does not print git"
  just --justfile "$target/Justfile" worktrees > /dev/null || fail "just worktrees failed"
  install tasker=gitwt
  [ "$(just --justfile "$target/Justfile" tasker-mode)" = gitwt ] || fail "just tasker-mode does not print gitwt"
  install --without tasker
  for gone in .agents/skills/gtw .claude/hooks .codex .agents/gest-git-install.json .agents/just/roles/agent_gest_git_skills.just; do
    if [ -e "$target/$gone" ]; then fail "$gone is still there after the removal"; fi
  done
  grep -q '"mine.sh"' "$target/.claude/settings.json" || fail "the removal dropped the hook of the user"
  if grep -q 'session-start' "$target/.claude/settings.json"; then fail "the removal left a Gest hook"; fi
  echo "install-test: install and removal passed"

lab-safety-test:
  uv run --no-project --quiet python -m unittest scripts/test_gitbutler_live_cleanup.py -q

ci-local: lint install-test lab-safety-test workflow-lab

integration-live:
  scripts/run_gitbutler_github_integration_lab.sh

diff-check:
  scripts/check_repo.sh --diff

verify: lint test diff-check
