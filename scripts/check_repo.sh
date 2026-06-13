#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${1:-all}"

required_files=(
  "README.md"
  "AGENTS.template.md"
  "CLAUDE.md"
  "Justfile"
  "skill-package.json"
  ".claude/settings.json"
  ".codex/hooks.json"
  "docs/README.md"
  "docs/TUTORIAL.md"
  "docs/live_gitbutler_tutorial_transcript_2026-05-07.md"
  "docs/gest_codex_workflow.md"
  "docs/tag_dependency_workflow.md"
  "docs/g_commands_cheatsheet.md"
  "docs/just_command_contract.md"
  "docs/agent_task_draft_workflow.md"
  "docs/live_agent_result_recursive_lab.md"
  "scripts/install.sh"
  "scripts/sync_g_skills.sh"
  "scripts/run_gitbutler_workflow_lab.sh"
  "scripts/run_gitbutler_github_integration_lab.sh"
  "scripts/run_tag_dependency_agent_dry_run.sh"
  "scripts/run_tag_dependency_typescript_lab.sh"
  "scripts/run_language_profile_labs.sh"
  "scripts/run_cx_examples_lab.sh"
  "scripts/run_agentic_target_lab.sh"
  "scripts/run_agent_result_lab.sh"
  "scripts/run_agent_task_draft_lab.sh"
  "scripts/run_agent_result_recursive_live_lab.sh"
  "scripts/jagt_lint_agent_task.sh"
  "scripts/jagt_lint_agent_task_draft.sh"
  "scripts/jagt_lint_agent_result.sh"
  "scripts/validate_agent_task.sh"
  "scripts/validate_agent_task_draft.sh"
  "scripts/validate_agent_result.sh"
  "fixtures/agent_task_draft/valid/result_pair.agent-task-draft.txt"
  "fixtures/agent_task_draft/invalid/malformed.agent-task-draft.txt"
  "fixtures/agent_task_draft/invalid/missing_approval.agent-task-draft.txt"
  "fixtures/agent_task_draft/invalid/missing_safety_language.agent-task-draft.txt"
  "fixtures/agent_task_draft/invalid/mode_agentic.agent-task-draft.txt"
  "fixtures/agent_task_draft/invalid/overbroad_allowed_actions.agent-task-draft.txt"
  "fixtures/agent_task_draft/invalid/direct_execution.agent-task-draft.txt"
  "fixtures/agent_task_draft/fresh_context/AGENTS.md"
  ".agents/skills/gest_git_installer/SKILL.md"
  ".agents/skills/gest_git_installer/scripts/install_gest_git_package.sh"
  "templates/README.md"
  "tools/gest_mermaid_graph.py"
)

for file in "${required_files[@]}"; do
  if [ ! -f "$repo_root/$file" ]; then
    echo "missing required file: $file" >&2
    exit 1
  fi
done

for skill in gbs gcm gdo gfm gest_git_installer gim gis gor gpa gpl gpr grv gsp gsu gte gtw; do
  if [ ! -f "$repo_root/.agents/skills/$skill/SKILL.md" ]; then
    echo "missing g skill: $skill" >&2
    exit 1
  fi
done

while IFS= read -r script; do
  bash -n "$script"
done < <(find "$repo_root/scripts" "$repo_root/.agents/skills" "$repo_root/.claude/hooks" "$repo_root/.codex/hooks" -type f -name '*.sh' | sort)

if command -v python3 >/dev/null 2>&1; then
  python3 -m json.tool "$repo_root/.claude/settings.json" >/dev/null
  python3 -m json.tool "$repo_root/.codex/hooks.json" >/dev/null
fi

required_text=(
  "but setup"
  "but branch new"
  "but branch new --anchor"
  "but commit"
  "but push"
  "Only step 3 uses GitButler"
  "ordinary git branch PR"
  "ordinary git multi-commit PR"
  "GitButler stacked PRs"
  "physical git worktrees"
  "Tags And ast-grep Dependency Check"
  "Pull Request Command Map"
  "but pr new tutorial/stack-child --default --json"
  "gh repo delete --yes"
  "Merge The Tutorial PRs"
  "PR acceptance checkpoint"
  "gh pr diff <number> --patch"
  "gh pr checks <number>"
  "gh pr merge <number> --merge --delete-branch"
  "state MERGED"
  "existing-tags.txt"
  "new dynamic tags: none"
  "vocabulary source"
  "After the agent finishes, check:"
  "classification.tags.reviewed"
  "impact.ast_grep.required"
  "count-or-probability-coloring"
  "probability-pill-colors"
  "tag-dependency-dry-run"
  "tag-dependency-live-lab"
  "ast-grep run"
  "Live TypeScript Tag And ast-grep Dependency Lab"
  "tag dependency expansion"
  "ast-grep dependency expansion"
  "run_tag_dependency_typescript_lab.sh"
  "git worktree add"
  "GitButler mode-strict"
  "GEST_VCS_EXECUTION=git-worktrees"
  "run_gitbutler_workflow_lab.sh"
  "run_gitbutler_github_integration_lab.sh"
  "run_language_profile_labs.sh"
  "language-profile-labs"
  "live local end-to-end"
  "cx Incremental Builds"
  "cx-examples-lab"
  "skill-package-maker"
  "skill-package.json"
  "uv --version"
  "rsync --version"
  "command -v uv"
  "command -v rsync"
  "run_cx_examples_lab.sh"
  "agentic-target-lab"
  "run_agentic_target_lab.sh"
  "jagt_lint_agent_task.sh"
  "validate_agent_task.sh"
  "AGENT_TASK v1"
  "agent-result-lab"
  "agent-result-recursive-live-lab"
  "run_agent_result_lab.sh"
  "run_agent_result_recursive_live_lab.sh"
  "jagt_lint_agent_result.sh"
  "validate_agent_result.sh"
  "AGENT_RESULT v1"
  "AGENT_RESULT is report-only"
  "agent-task-draft-lab"
  "run_agent_task_draft_lab.sh"
  "jagt_lint_agent_task_draft.sh"
  "validate_agent_task_draft.sh"
  "AGENT_TASK_DRAFT v1"
  "jagt draft lint"
  "legacy shell reference"
  "stochastic task proposals"
  "proposal, not executable"
  "approval.required: true"
  "jagt render"
  "jagt lint"
  "final_agent_task_lints"
  "fresh-context"
  "direct draft execution rejection"
  "expected target/status"
  "required file"
  "proposed_tasks"
  "parent-orchestrated"
  "local-recursion-supported"
  "Live AGENT_RESULT Recursive Lab"
  "two successive subagents"
  "planner subagent"
  "worker subagent"
  "unsafe proposal"
  "wc -w"
  "Subagent Execution Boundary"
  "Subagent Result Boundary"
  "subagent handoff"
  "subagent result"
  "hook-triggered packets"
  "agentic verification targets"
  "nested agentic Just calls"
  "agentic dependencies"
  "Artifact Pipeline"
  "Incremental C Build"
  "Python With UV"
  "TypeScript With NPM"
  "Rust With Cargo"
)

for needle in "${required_text[@]}"; do
  if ! grep -R "$needle" "$repo_root/AGENTS.template.md" "$repo_root/README.md" "$repo_root/docs" "$repo_root/.agents/skills" "$repo_root/scripts" >/dev/null; then
    echo "missing required GitButler workflow text: $needle" >&2
    exit 1
  fi
done

for stale_tutorial_text in "Latest Live Run" "422 Unprocessable Entity" "live_gitbutler_tutorial_transcript"; do
  if grep -q "$stale_tutorial_text" "$repo_root/docs/TUTORIAL.md"; then
    echo "stale run/debugging text remains in docs/TUTORIAL.md: $stale_tutorial_text" >&2
    exit 1
  fi
done

claude_deny="$(printf '{"command":"git commit -m nope"}' | "$repo_root/.claude/hooks/raw-git-write-guard.sh" || true)"
if ! printf '%s' "$claude_deny" | grep -q 'permissionDecision'; then
  echo "Claude raw git guard did not deny git commit" >&2
  exit 1
fi

claude_allow="$(printf '{"command":"but commit demo -m ok"}' | "$repo_root/.claude/hooks/raw-git-write-guard.sh" || true)"
if [ -n "$claude_allow" ]; then
  echo "Claude raw git guard denied but commit" >&2
  exit 1
fi

codex_deny="$(printf '{"tool_input":{"command":"git commit -m nope"}}' | "$repo_root/.codex/hooks/raw-git-write-guard.sh" || true)"
if ! printf '%s' "$codex_deny" | grep -q 'permissionDecision'; then
  echo "Codex raw git guard did not deny git commit" >&2
  exit 1
fi

codex_allow="$(printf '{"tool_input":{"command":"but commit demo -m ok"}}' | "$repo_root/.codex/hooks/raw-git-write-guard.sh" || true)"
if [ -n "$codex_allow" ]; then
  echo "Codex raw git guard denied but commit" >&2
  exit 1
fi

claude_worktree_allow="$(printf '{"command":"GEST_VCS_EXECUTION=git-worktrees git worktree add -b demo /tmp/demo main"}' | "$repo_root/.claude/hooks/raw-git-write-guard.sh" || true)"
if [ -n "$claude_worktree_allow" ]; then
  echo "Claude raw git guard denied explicit physical worktree command" >&2
  exit 1
fi

codex_worktree_allow="$(printf '{"tool_input":{"command":"GEST_VCS_EXECUTION=git-worktrees git worktree add -b demo /tmp/demo main"}}' | "$repo_root/.codex/hooks/raw-git-write-guard.sh" || true)"
if [ -n "$codex_worktree_allow" ]; then
  echo "Codex raw git guard denied explicit physical worktree command" >&2
  exit 1
fi

if [ "$mode" = "--diff" ]; then
  git -C "$repo_root" diff --check
fi

echo "repository checks passed"
