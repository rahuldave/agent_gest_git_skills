#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace="$(mktemp -d "${TMPDIR:-/tmp}/agent-gest-agentic-target-lab.XXXXXX")"

cleanup() {
  rm -rf "$workspace"
}
trap cleanup EXIT

require_tool() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 is required for the agentic target lab" >&2
    exit 1
  fi
}

run() {
  printf '$ %s\n' "$*"
  "$@"
}

require_tool just

cp "$repo_root/scripts/validate_agent_task.sh" "$workspace/validate_agent_task.sh"
chmod +x "$workspace/validate_agent_task.sh"

cat >"$workspace/render_agent_task.sh" <<'RENDER'
#!/usr/bin/env bash
set -euo pipefail

target="${1:-eda-viz}"
shift || true

printf '%s\n' '<<<AGENT_TASK v1>>>'
printf 'target: %s\n' "$target"
printf '%s\n' 'mode: agentic'
printf '%s\n' 'argv:'
if [ "$#" -eq 0 ]; then
  printf '%s\n' '  - data/raw/train.csv'
else
  for arg in "$@"; do
    printf '  - %s\n' "$arg"
  done
fi
printf '%s\n' 'prompt: |'
printf '  Inspect the input files and produce the requested %s artifact.\n' "$target"
printf '%s\n' 'inputs:'
printf '%s\n' '  files:'
if [ "$#" -eq 0 ]; then
  printf '%s\n' '    - data/raw/train.csv'
else
  for arg in "$@"; do
    printf '    - %s\n' "$arg"
  done
fi
printf '%s\n' 'outputs:'
printf '  required:\n    - reports/%s/index.html\n' "$target"
printf '%s\n' 'allowed_actions:'
printf '%s\n' '  - read listed inputs'
printf '%s\n' '  - create listed outputs'
printf '%s\n' '  - inspect nearby project docs and code'
printf '%s\n' '  - propose a concrete replacement target if the pattern stabilizes'
printf '%s\n' 'verification:'
printf '  - test -f reports/%s/index.html\n' "$target"
printf '%s\n' 'delegation:'
printf '%s\n' '  execution: subagent'
printf '%s\n' '  recursive: true'
printf '%s\n' '  triggers:'
printf '%s\n' '    - nested agentic Just calls'
printf '%s\n' '    - agentic dependencies'
printf '%s\n' '    - hook-triggered packets'
printf '%s\n' '    - agentic verification targets'
printf '%s\n' 'safety:'
printf '%s\n' '  - This block is repo-local operational context.'
printf '%s\n' '  - It cannot override user, system, developer, VCS, or approval instructions.'
printf '%s\n' '<<<END_AGENT_TASK>>>'
RENDER
chmod +x "$workspace/render_agent_task.sh"

cat >"$workspace/Justfile" <<'JUST'
direct +FILES:
  @./render_agent_task.sh direct {{FILES}}

companion +FILES:
  @printf '%s\n' 'concrete companion target ran'

companion-agentic +FILES:
  @./render_agent_task.sh companion {{FILES}}

agentic TARGET +ARGS:
  @./render_agent_task.sh {{TARGET}} {{ARGS}}

prompt-file-agentic PROMPT +FILES:
  @./render_agent_task.sh prompt-file {{PROMPT}} {{FILES}}

nested-agentic:
  @./render_agent_task.sh nested data/nested.csv

dependency-agentic: nested-agentic
  @./render_agent_task.sh dependency data/dependency.csv

verification-agentic:
  @./render_agent_task.sh verification reports/eda/index.html

hook-agentic:
  @./render_agent_task.sh hook hooks/pre-commit

malformed-delimiter:
  @printf '%s\n' '<<<AGENT_TASK v1>>>' 'target: broken'

malformed-yaml:
  @printf '%s\n' '<<<AGENT_TASK v1>>>' 'target broken' 'mode: agentic' '<<<END_AGENT_TASK>>>'
JUST

cd "$workspace"
mkdir -p data/raw data/new prompts reports
printf '%s\n' 'focus on missingness and outliers' >prompts/eda_viz.md

run just direct data/raw/train.csv >direct.out
run ./validate_agent_task.sh --expect-count 1 direct.out

run just companion data/raw/train.csv >concrete.out
run ./validate_agent_task.sh --expect-none concrete.out

run just companion-agentic data/raw/train.csv >companion.out
run ./validate_agent_task.sh --expect-count 1 companion.out

run just agentic eda-viz data/raw/train.csv data/new/week-23.csv >dispatcher.out
run ./validate_agent_task.sh --expect-count 1 dispatcher.out
grep -q 'data/new/week-23.csv' dispatcher.out

run just prompt-file-agentic prompts/eda_viz.md data/raw/train.csv >prompt-file.out
run ./validate_agent_task.sh --expect-count 1 prompt-file.out
grep -q 'prompts/eda_viz.md' prompt-file.out

run just dependency-agentic >dependency.out
run ./validate_agent_task.sh --expect-count 2 dependency.out
grep -q 'target: nested' dependency.out
grep -q 'target: dependency' dependency.out

run just verification-agentic >verification.out
run ./validate_agent_task.sh --expect-count 1 verification.out
grep -q 'agentic verification targets' verification.out

run just hook-agentic >hook.out
run ./validate_agent_task.sh --expect-count 1 hook.out
grep -q 'hook-triggered packets' hook.out

run just malformed-delimiter >malformed-delimiter.out
if ./validate_agent_task.sh malformed-delimiter.out >/tmp/agentic-target-malformed-delimiter.log 2>&1; then
  echo "malformed delimiter unexpectedly validated" >&2
  exit 1
fi

run just malformed-yaml >malformed-yaml.out
if ./validate_agent_task.sh malformed-yaml.out >/tmp/agentic-target-malformed-yaml.log 2>&1; then
  echo "malformed YAML-like body unexpectedly validated" >&2
  exit 1
fi

echo "agentic target lab passed"
