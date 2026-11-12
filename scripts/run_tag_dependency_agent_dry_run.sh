#!/usr/bin/env bash
set -euo pipefail

if ! command -v ast-grep >/dev/null 2>&1; then
  echo "ast-grep is required for the tag/dependency agent dry run" >&2
  exit 1
fi

work_root="${TMPDIR:-/tmp}/agent-gest-tag-dependency-agent"
fixture="$work_root/src"
rm -rf "$work_root"
mkdir -p "$fixture"

cat >"$fixture/colors.js" <<'JS'
export function countOrProbabilityColorScale(value) {
  if (value < 0.2) return "blue";
  if (value < 0.7) return "green";
  return "red";
}
JS

cat >"$fixture/histogram.js" <<'JS'
import { countOrProbabilityColorScale } from "./colors.js";

export function renderHistogramBin(bin) {
  return {
    count: bin.count,
    fill: countOrProbabilityColorScale(bin.probability),
  };
}
JS

cat >"$fixture/pill.js" <<'JS'
import { countOrProbabilityColorScale } from "./colors.js";

export function probabilityPill(probability) {
  return {
    label: `${Math.round(probability * 100)}%`,
    color: countOrProbabilityColorScale(probability),
  };
}
JS

cat >"$work_root/existing-tags.txt" <<'TAGS'
histogram-colors
probability-pill-colors
count-or-probability-coloring
reader-ui
docs
TAGS

pattern='countOrProbabilityColorScale($$$)'
result_file="$work_root/ast-grep-results.jsonl"

ast-grep run --lang javascript   --pattern "$pattern"   --json=compact "$fixture" >"$result_file"

if ! grep -q 'histogram.js' "$result_file"; then
  echo "agent dry run missed histogram.js depender" >&2
  cat "$result_file" >&2
  exit 1
fi

if ! grep -q 'pill.js' "$result_file"; then
  echo "agent dry run missed pill.js depender" >&2
  cat "$result_file" >&2
  exit 1
fi

cat <<'TEXT'
Agent dry run: tag classification
- vocabulary source: seeded existing-tags fixture, standing in for Gest task/artifact/iteration tag collection
- selected existing tag: count-or-probability-coloring
- selected existing tag: histogram-colors
- selected existing tag: probability-pill-colors
- rejected near miss: reader-ui, because the prompt targeted shared color semantics rather than a full reader interaction change
- new dynamic tags: none

Agent dry run: ast-grep dependency impact
- changed contract: countOrProbabilityColorScale
- pattern: countOrProbabilityColorScale($$$)
- dependers found: histogram.js, pill.js
- required task expansion: update the pill color surface with the histogram color change, or create a tagged child task before completion
TEXT

rm -rf "$work_root"
