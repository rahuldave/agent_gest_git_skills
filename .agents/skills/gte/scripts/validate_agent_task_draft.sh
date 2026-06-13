#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/validate_agent_task_draft.sh [--expect-none] [--expect-count N] <file>

Validate AGENT_TASK_DRAFT v1 proposal envelopes emitted by stochastic task
design subagents.
USAGE
}

expect_none=0
expect_count=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --expect-none)
      expect_none=1
      shift
      ;;
    --expect-count)
      if [ "$#" -lt 2 ]; then
        usage
        exit 2
      fi
      expect_count="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      usage
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

if [ "$#" -ne 1 ]; then
  usage
  exit 2
fi

input_file="$1"

if [ ! -f "$input_file" ]; then
  echo "missing input file: $input_file" >&2
  exit 2
fi

start_marker="<<<AGENT_TASK_DRAFT v1>>>"
end_marker="<<<END_AGENT_TASK_DRAFT>>>"

fail() {
  echo "invalid AGENT_TASK_DRAFT block: $*" >&2
  exit 1
}

contains() {
  local body="$1"
  local pattern="$2"
  printf '%s\n' "$body" | grep -Eq "$pattern"
}

field_count() {
  local body="$1"
  local field="$2"
  printf '%s\n' "$body" | grep -Ec "^${field}:"
}

validate_block() {
  local body="$1"
  local index="$2"

  [ "$(field_count "$body" target)" -eq 1 ] || fail "block $index must contain exactly one target"
  [ "$(field_count "$body" mode)" -eq 1 ] || fail "block $index must contain exactly one mode"

  contains "$body" '^target: [A-Za-z0-9_.-]+$' || fail "block $index missing valid target"
  contains "$body" '^mode: draft$' || fail "block $index must use mode: draft"
  contains "$body" '^generator:$' || fail "block $index missing generator"
  contains "$body" '^[[:space:]]+kind: llm$' || fail "block $index generator must declare kind: llm"
  contains "$body" '^[[:space:]]+execution: subagent$' || fail "block $index generator must declare subagent execution"
  contains "$body" '^proposal_reason: \|$' || fail "block $index missing proposal_reason"
  contains "$body" '^prompt: \|$' || fail "block $index missing prompt"
  contains "$body" '^inputs:$' || fail "block $index missing inputs"
  contains "$body" '^outputs:$' || fail "block $index missing outputs"
  contains "$body" '^allowed_actions:$' || fail "block $index missing allowed_actions"
  contains "$body" '^verification:$' || fail "block $index missing verification"
  contains "$body" '^approval:$' || fail "block $index missing approval"
  contains "$body" '^[[:space:]]+required: true$' || fail "block $index approval.required must be true"
  contains "$body" '^promotion:$' || fail "block $index missing promotion"
  contains "$body" '^[[:space:]]+method: jagt-render$' || fail "block $index promotion method must be jagt-render"
  contains "$body" 'draft_shape_valid' || fail "block $index missing draft_shape_valid promotion check"
  contains "$body" 'policy_review_passed' || fail "block $index missing policy_review_passed promotion check"
  contains "$body" 'approval_recorded' || fail "block $index missing approval_recorded promotion check"
  contains "$body" 'final_agent_task_lints' || fail "block $index missing final_agent_task_lints promotion check"
  contains "$body" '^delegation:$' || fail "block $index missing delegation"
  contains "$body" '^[[:space:]]+execution_after_promotion: subagent$' || fail "block $index final execution must use a subagent"
  contains "$body" '^[[:space:]]+recursive: true$' || fail "block $index must declare recursive delegation"
  contains "$body" '^safety:$' || fail "block $index missing safety"
  contains "$body" 'proposal, not executable' || fail "block $index missing non-executable safety text"
  contains "$body" 'cannot override user, system, developer, VCS, approval, or repo instructions' || fail "block $index missing non-override safety text"
  contains "$body" 'cannot expand authority beyond the source request' || fail "block $index missing no-authority-expansion safety text"

  if printf '%s\n' "$body" | grep -Eq '^mode: agentic$'; then
    fail "block $index uses executable mode: agentic"
  fi

  if printf '%s\n' "$body" | grep -Eiq '(^|[[:space:]])approved: true|already approved|preapproved|pre-approved'; then
    fail "block $index claims the draft is already approved"
  fi

  if printf '%s\n' "$body" | grep -Eiq 'bypass (approval|approvals|sandbox|sandboxing|user|system|developer|vcs|repo|repository|policy)'; then
    fail "block $index attempts to bypass approvals or policy"
  fi

  if printf '%s\n' "$body" | grep -Eiq 'write anywhere|read all files|read arbitrary|unrestricted|any command|network access'; then
    fail "block $index contains overbroad allowed actions"
  fi

  if printf '%s\n' "$body" | grep -Eiq 'execute_inline: true|execution_after_promotion: (parent|current-agent|same-subagent|self|inline)|execute .*inline|run .*inline|perform .*inline'; then
    fail "block $index attempts direct draft execution"
  fi

  if printf '%s\n' "$body" | grep -Eq '^[A-Za-z_][A-Za-z0-9_.-]*[[:space:]][^:]+$'; then
    fail "block $index contains malformed top-level YAML-like field"
  fi

  local open_square close_square open_curly close_curly
  open_square="$(printf '%s\n' "$body" | tr -cd '[' | wc -c | tr -d ' ')"
  close_square="$(printf '%s\n' "$body" | tr -cd ']' | wc -c | tr -d ' ')"
  open_curly="$(printf '%s\n' "$body" | tr -cd '{' | wc -c | tr -d ' ')"
  close_curly="$(printf '%s\n' "$body" | tr -cd '}' | wc -c | tr -d ' ')"
  [ "$open_square" = "$close_square" ] || fail "block $index has unbalanced square brackets"
  [ "$open_curly" = "$close_curly" ] || fail "block $index has unbalanced curly braces"
}

if [ "$expect_none" -eq 1 ]; then
  if grep -q "$start_marker" "$input_file" || grep -q "$end_marker" "$input_file"; then
    fail "expected no AGENT_TASK_DRAFT block"
  fi
  echo "no agent task draft blocks detected"
  exit 0
fi

block_count=0
in_block=0
body=""

while IFS= read -r line || [ -n "$line" ]; do
  if [ "$line" = "$start_marker" ]; then
    [ "$in_block" -eq 0 ] || fail "nested start marker"
    in_block=1
    body=""
    continue
  fi

  if [ "$line" = "$end_marker" ]; then
    [ "$in_block" -eq 1 ] || fail "end marker without start marker"
    block_count=$((block_count + 1))
    validate_block "$body" "$block_count"
    in_block=0
    body=""
    continue
  fi

  if [ "$in_block" -eq 1 ]; then
    body="${body}${line}"$'\n'
  fi
done <"$input_file"

[ "$in_block" -eq 0 ] || fail "start marker without end marker"
[ "$block_count" -gt 0 ] || fail "no AGENT_TASK_DRAFT block found"

if [ -n "$expect_count" ] && [ "$block_count" -ne "$expect_count" ]; then
  fail "expected $expect_count block(s), found $block_count"
fi

echo "validated $block_count AGENT_TASK_DRAFT block(s)"
