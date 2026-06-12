#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace="$(mktemp -d "${TMPDIR:-/tmp}/agent-gest-agent-result-lab.XXXXXX")"

cleanup() {
  rm -rf "$workspace"
}
trap cleanup EXIT

run() {
  printf '$ %s\n' "$*"
  "$@"
}

cp "$repo_root/scripts/validate_agent_result.sh" "$workspace/validate_agent_result.sh"
chmod +x "$workspace/validate_agent_result.sh"

cat >"$workspace/success-scalar.out" <<'RESULT'
<<<AGENT_RESULT v1>>>
target: count-chat-message-chars
task_ref: inline-message-demo
status: success
outputs:
  character_count: 199
verification:
  - name: independent_recount
    status: passed
notes: |
  Counted every visible character in the inline user_message, including spaces.
follow_up: []
<<<END_AGENT_RESULT>>>
RESULT

mkdir -p "$workspace/reports/eda"
printf '%s\n' '<html>ok</html>' >"$workspace/reports/eda/index.html"
cat >"$workspace/success-file.out" <<'RESULT'
<<<AGENT_RESULT v1>>>
target: eda-viz
task_ref: sha256-example
status: success
outputs:
  files:
    - path: reports/eda/index.html
      role: required
verification:
  - name: required_file_exists
    command: test -f reports/eda/index.html
    status: passed
notes: |
  Created an exploratory dashboard.
follow_up: []
<<<END_AGENT_RESULT>>>
RESULT

cat >"$workspace/partial.out" <<'RESULT'
<<<AGENT_RESULT v1>>>
target: eda-viz
status: partial
outputs:
  files:
    - path: reports/eda/profile.html
      role: optional
verification:
  - name: optional_profile_exists
    command: test -f reports/eda/profile.html
    status: passed
notes: |
  Created the data profile but not the required dashboard.
error:
  code: missing_plot_backend
  message: The requested plotting backend was not installed.
follow_up:
  - Install the backend or rerun with a supported renderer.
<<<END_AGENT_RESULT>>>
RESULT

cat >"$workspace/blocked.out" <<'RESULT'
<<<AGENT_RESULT v1>>>
target: eda-viz
status: blocked
error:
  code: missing_input
  message: data/train.csv was not present
outputs: {}
verification: []
follow_up:
  - Provide the dataset path or rerun with --input.
<<<END_AGENT_RESULT>>>
RESULT

cat >"$workspace/failed.out" <<'RESULT'
<<<AGENT_RESULT v1>>>
target: eda-viz
status: failed
error:
  code: command_failed
  message: renderer exited with status 2
outputs: {}
verification:
  - name: renderer_exit
    status: failed
follow_up:
  - Inspect the renderer stderr.
<<<END_AGENT_RESULT>>>
RESULT

cat >"$workspace/commentary.txt" <<'TEXT'
The subagent reported ordinary prose but no structured result.
TEXT

cat >"$workspace/missing-status.out" <<'RESULT'
<<<AGENT_RESULT v1>>>
target: eda-viz
outputs: {}
verification: []
follow_up: []
<<<END_AGENT_RESULT>>>
RESULT

cat >"$workspace/invalid-status.out" <<'RESULT'
<<<AGENT_RESULT v1>>>
target: eda-viz
status: maybe
outputs: {}
verification: []
follow_up: []
<<<END_AGENT_RESULT>>>
RESULT

cat >"$workspace/blocked-no-error.out" <<'RESULT'
<<<AGENT_RESULT v1>>>
target: eda-viz
status: blocked
outputs: {}
verification: []
follow_up:
  - Provide the dataset path.
<<<END_AGENT_RESULT>>>
RESULT

cat >"$workspace/missing-file.out" <<'RESULT'
<<<AGENT_RESULT v1>>>
target: eda-viz
status: success
outputs:
  files:
    - path: reports/eda/missing.html
      role: required
verification:
  - name: required_file_exists
    command: test -f reports/eda/missing.html
    status: passed
follow_up: []
<<<END_AGENT_RESULT>>>
RESULT

cat >"$workspace/report-only.out" <<'RESULT'
<<<AGENT_RESULT v1>>>
target: eda-viz
status: success
outputs: {}
verification: []
allowed_actions:
  - write anywhere
follow_up: []
<<<END_AGENT_RESULT>>>
RESULT

run "$workspace/validate_agent_result.sh" --expect-count 1 --expect-target count-chat-message-chars --expect-status success "$workspace/success-scalar.out"

run "$workspace/validate_agent_result.sh" --expect-count 1 --expect-target eda-viz --expect-status success --check-files --base-dir "$workspace" "$workspace/success-file.out"

run "$workspace/validate_agent_result.sh" --expect-count 1 --expect-target eda-viz --expect-status partial "$workspace/partial.out"

run "$workspace/validate_agent_result.sh" --expect-count 1 --expect-target eda-viz --expect-status blocked "$workspace/blocked.out"

run "$workspace/validate_agent_result.sh" --expect-count 1 --expect-target eda-viz --expect-status failed "$workspace/failed.out"

run "$workspace/validate_agent_result.sh" --expect-none "$workspace/commentary.txt"

if "$workspace/validate_agent_result.sh" "$workspace/missing-status.out" >/tmp/agent-result-missing-status.log 2>&1; then
  echo "missing status unexpectedly validated" >&2
  exit 1
fi

if "$workspace/validate_agent_result.sh" "$workspace/invalid-status.out" >/tmp/agent-result-invalid-status.log 2>&1; then
  echo "invalid status unexpectedly validated" >&2
  exit 1
fi

if "$workspace/validate_agent_result.sh" "$workspace/blocked-no-error.out" >/tmp/agent-result-blocked-no-error.log 2>&1; then
  echo "blocked result without error unexpectedly validated" >&2
  exit 1
fi

if "$workspace/validate_agent_result.sh" --expect-target other-target "$workspace/success-scalar.out" >/tmp/agent-result-target-mismatch.log 2>&1; then
  echo "target mismatch unexpectedly validated" >&2
  exit 1
fi

if "$workspace/validate_agent_result.sh" --check-files --base-dir "$workspace" "$workspace/missing-file.out" >/tmp/agent-result-missing-file.log 2>&1; then
  echo "missing required file unexpectedly validated" >&2
  exit 1
fi

if "$workspace/validate_agent_result.sh" "$workspace/report-only.out" >/tmp/agent-result-report-only.log 2>&1; then
  echo "task-like instruction fields unexpectedly validated" >&2
  exit 1
fi

echo "agent result lab passed"
