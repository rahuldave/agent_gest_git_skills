#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace="$(mktemp -d "${TMPDIR:-/tmp}/agent-gest-agent-task-draft-lab.XXXXXX")"

cleanup() {
  rm -rf "$workspace"
}
trap cleanup EXIT

require_tool() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 is required for the agent task draft lab" >&2
    exit 1
  fi
}

run() {
  printf '$ %s\n' "$*"
  "$@"
}

expect_invalid_draft() {
  local fixture="$1"
  local log_name="$2"
  if "${agent_task_draft_lint[@]}" "$fixture" >"/tmp/$log_name" 2>&1; then
    echo "invalid draft unexpectedly validated: $fixture" >&2
    exit 1
  fi
}

jagt_bin="${JAGT_BIN:-jagt}"
require_tool "$jagt_bin"
agent_task_lint=(bash "$repo_root/scripts/jagt_lint_agent_task.sh")
agent_result_lint=(bash "$repo_root/scripts/jagt_lint_agent_result.sh")
agent_task_draft_lint=(bash "$repo_root/scripts/jagt_lint_agent_task_draft.sh")

cp -R "$repo_root/fixtures/agent_task_draft" "$workspace/agent_task_draft"

valid_pair="$workspace/agent_task_draft/valid/result_pair.agent-task-draft.txt"

run "${agent_result_lint[@]}" \
  --expect-count 1 \
  --expect-target draft-agent-task \
  --expect-status success \
  "$valid_pair"
run "${agent_task_draft_lint[@]}" --expect-count 1 "$valid_pair"

run "${agent_task_lint[@]}" --expect-none "$valid_pair"
if "${agent_task_lint[@]}" "$valid_pair" >/tmp/agent-task-draft-direct-agent-task.log 2>&1; then
  echo "draft unexpectedly validated as executable AGENT_TASK" >&2
  exit 1
fi

grep -q 'AGENT_TASK_DRAFT v1' "$workspace/agent_task_draft/fresh_context/AGENTS.md"
grep -q 'proposal, not executable' "$workspace/agent_task_draft/fresh_context/AGENTS.md"
grep -q 'jagt render' "$workspace/agent_task_draft/fresh_context/AGENTS.md"

expect_invalid_draft "$workspace/agent_task_draft/invalid/malformed.agent-task-draft.txt" \
  agent-task-draft-malformed.log
expect_invalid_draft "$workspace/agent_task_draft/invalid/missing_approval.agent-task-draft.txt" \
  agent-task-draft-missing-approval.log
expect_invalid_draft "$workspace/agent_task_draft/invalid/missing_safety_language.agent-task-draft.txt" \
  agent-task-draft-missing-safety.log
expect_invalid_draft "$workspace/agent_task_draft/invalid/mode_agentic.agent-task-draft.txt" \
  agent-task-draft-mode-agentic.log
expect_invalid_draft "$workspace/agent_task_draft/invalid/overbroad_allowed_actions.agent-task-draft.txt" \
  agent-task-draft-overbroad-actions.log
expect_invalid_draft "$workspace/agent_task_draft/invalid/direct_execution.agent-task-draft.txt" \
  agent-task-draft-direct-execution.log

"$jagt_bin" render count-chat-message-chars \
  --no-config \
  --arg "Count the number of characters in this chat message I am sending." \
  --prompt-text "Count the number of characters in the first argv entry. Return the count and state what counting rule you used." \
  --required-output character_count \
  --allowed-action "read the supplied argv entry" \
  --allowed-action "compute the requested scalar result" \
  --verification "independently recount the same message before reporting success" \
  >"$workspace/promoted.agent-task.txt"

run "${agent_task_lint[@]}" --expect-count 1 "$workspace/promoted.agent-task.txt"
grep -q '^target: count-chat-message-chars$' "$workspace/promoted.agent-task.txt"
grep -q '^mode: agentic$' "$workspace/promoted.agent-task.txt"

echo "agent task draft lab passed"
