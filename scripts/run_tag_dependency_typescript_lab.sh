#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tutorial_root="${AGENT_GEST_TUTORIAL_ROOT:-/tmp/agent-gest-git-tutorial}"
lab_root="${1:-$tutorial_root/tag-ast-grep-live}"
log_file="${2:-$tutorial_root/logs/05-tag-ast-grep.log}"

# A ".." could take the path out of the temp folder, and rm -rf follows it.
case "/$lab_root/" in
  */../*|*/./*)
    echo "refusing a lab root with a . or .. part: $lab_root" >&2
    exit 1
    ;;
esac

allowed_root() {
  case "$1" in
    /tmp/agent-gest-*|/private/tmp/agent-gest-*|/var/folders/*/agent-gest-*|/private/var/folders/*/agent-gest-*|/tmp/*/agent-gest-*|/private/tmp/*/agent-gest-*)
      return 0
      ;;
  esac
  return 1
}

if ! allowed_root "$lab_root"; then
  echo "refusing to recreate lab root outside an agent-gest temp path: $lab_root" >&2
  exit 1
fi

# A folder of the path can be a link, and rm -rf follows it. So check the real
# path too: the real path of the deepest folder that exists, then the rest.
if [ -L "$lab_root" ]; then
  echo "refusing a lab root that is a link: $lab_root" >&2
  exit 1
fi
existing="$(dirname "$lab_root")"
rest="$(basename "$lab_root")"
while [ ! -d "$existing" ]; do
  rest="$(basename "$existing")/$rest"
  existing="$(dirname "$existing")"
done
real_root="$(cd -P "$existing" && pwd -P)/$rest"
if ! allowed_root "$real_root"; then
  echo "refusing a lab root whose real path is outside an agent-gest temp path: $lab_root is $real_root" >&2
  exit 1
fi

# The typescript profile of jnterfaces sets up the TypeScript tools of the lab.
jnterfaces_dir="${JNTERFACES_DIR:-$repo_root/../jnterfaces}"
if [ ! -f "$jnterfaces_dir/scripts/install_stack.py" ]; then
  echo "The lab needs a jnterfaces clone at $jnterfaces_dir. Clone https://github.com/rahuldave/jnterfaces there, or set JNTERFACES_DIR." >&2
  exit 1
fi

require_tool() {
  local tool="$1"
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "missing required tool: $tool" >&2
    exit 1
  fi
}

run() {
  printf '\n$ %s\n' "$*"
  "$@"
}

require_tool git
require_tool gest
require_tool just
require_tool uv
require_tool npm
require_tool node
require_tool ast-grep

rm -rf "$lab_root"
mkdir -p "$lab_root/src" "$(dirname "$log_file")"

exec > >(tee "$log_file") 2>&1

cd "$lab_root"
echo "Live TypeScript Tag And ast-grep Dependency Lab"
echo "repo: $lab_root"
echo "log: $log_file"

run git -c init.defaultBranch=main init
run git config user.name tutorial-agent
run git config user.email tutorial-agent@example.invalid
run gest init --local

run gest task create "Shared count/probability color contract" \
  -d "Shared semantic color scale used by both histogram bins and probability pills." \
  --tag count-or-probability-coloring \
  --tag design \
  --quiet

run gest task create "Render histogram bin colors" \
  -d "Histogram bars use the shared count/probability color contract." \
  --tag count-or-probability-coloring \
  --tag histogram-colors \
  --quiet

run gest task create "Render probability pill colors" \
  -d "Probability pills use the same shared count/probability color contract." \
  --tag count-or-probability-coloring \
  --tag probability-pill-colors \
  --quiet

run gest task create "Polish reader hover affordance" \
  -d "Nearby reader UI work that should not be selected for this semantic color change." \
  --tag reader-ui \
  --quiet

# The installer writes package.json, tsconfig.json and the Justfile of the
# typescript profile, with its typecheck tool. The lab installs no role, so
# no commit gate stops the commit of the fixture.
run uv run "$jnterfaces_dir/scripts/install_stack.py" \
  --target "$lab_root" \
  --profile typescript \
  typecheck

cat >src/colors.ts <<'TYPESCRIPT'
export type ColorToken = "blue" | "green" | "red";

export function countOrProbabilityColorScale(value: number): ColorToken {
  if (value < 0.2) return "blue";
  if (value < 0.7) return "green";
  return "red";
}
TYPESCRIPT

cat >src/histogram.ts <<'TYPESCRIPT'
import { countOrProbabilityColorScale } from "./colors";

export interface HistogramBin {
  label: string;
  count: number;
  probability: number;
}

export function renderHistogramBin(bin: HistogramBin): { label: string; fill: string } {
  return {
    label: bin.label,
    fill: countOrProbabilityColorScale(bin.probability),
  };
}
TYPESCRIPT

cat >src/pill.ts <<'TYPESCRIPT'
import { countOrProbabilityColorScale } from "./colors";

export function probabilityPill(probability: number): { label: string; color: string } {
  return {
    label: `${Math.round(probability * 100)}%`,
    color: countOrProbabilityColorScale(probability),
  };
}
TYPESCRIPT

cat >src/readerHover.ts <<'TYPESCRIPT'
export function readerHoverClass(isActive: boolean): string {
  return isActive ? "reader-hover-active" : "reader-hover-idle";
}
TYPESCRIPT

run just typecheck

printf '\n$ gest task list --all --json > gest-tasks.json\n'
gest task list --all --json >gest-tasks.json
printf '$ gest artifact list --all --json > gest-artifacts.json\n'
gest artifact list --all --json >gest-artifacts.json
printf '$ gest iteration list --all --json > gest-iterations.json\n'
gest iteration list --all --json >gest-iterations.json

node <<'NODE' >tag-impact.txt
const fs = require("node:fs");
const tasks = JSON.parse(fs.readFileSync("gest-tasks.json", "utf8"));
const allTags = [...new Set(tasks.flatMap((task) => task.tags || []))].sort();
const selectedTags = [
  "count-or-probability-coloring",
  "histogram-colors",
  "probability-pill-colors",
];
const rejectedTags = ["reader-ui"];
const impacted = tasks
  .filter((task) => (task.tags || []).includes("count-or-probability-coloring"))
  .map((task) => `${task.title} [${(task.tags || []).join(", ")}]`)
  .sort()
  .filter((title, index, titles) => title !== titles[index - 1]);

console.log("tag dependency expansion");
console.log(`vocabulary source: gest task list --all --json`);
console.log(`existing tags: ${allTags.join(", ")}`);
for (const tag of selectedTags) console.log(`selected existing tag: ${tag}`);
for (const tag of rejectedTags) console.log(`rejected near miss: ${tag}`);
console.log("new dynamic tags: none");
console.log("tag-linked work:");
for (const title of impacted) console.log(`- ${title}`);
NODE

pattern='countOrProbabilityColorScale($$$)'
run ast-grep run --lang typescript --pattern "$pattern" --json=compact src
ast-grep run --lang typescript --pattern "$pattern" --json=compact src >ast-grep-results.jsonl

if ! grep -q 'src/histogram.ts' ast-grep-results.jsonl; then
  echo "ast-grep missed src/histogram.ts" >&2
  exit 1
fi

if ! grep -q 'src/pill.ts' ast-grep-results.jsonl; then
  echo "ast-grep missed src/pill.ts" >&2
  exit 1
fi

if grep -q 'src/readerHover.ts' ast-grep-results.jsonl; then
  echo "ast-grep incorrectly matched unrelated readerHover.ts" >&2
  exit 1
fi

cat tag-impact.txt

cat <<TEXT

ast-grep dependency expansion
changed contract: countOrProbabilityColorScale
pattern: $pattern
semantic callers:
- src/histogram.ts
- src/pill.ts
not matched:
- src/readerHover.ts

Conclusion
A request phrased as "change histogram colors for low-count bins" selects the
histogram tag, but the shared count/probability color tag and the ast-grep
call graph both show that probability pills depend on the same contract. The
agent must either include the pill color surface in the implementation or create
a tagged child task before completing the work.
TEXT

run git add -A
run git commit -m "test: create tag and ast-grep dependency fixture"

echo "live TypeScript tag/ast-grep lab passed"
