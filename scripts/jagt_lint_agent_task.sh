#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/jagt_lint_agent_task.sh [--expect-none] [--expect-count N] <file>

Validate AGENT_TASK v1 envelopes with jagt. This is the maintained verifier;
scripts/validate_agent_task.sh remains as a legacy shell reference.
USAGE
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

jagt_bin="${JAGT_BIN:-jagt}"
if ! command -v "$jagt_bin" >/dev/null 2>&1; then
  echo "$jagt_bin is required for AGENT_TASK v1 linting" >&2
  exit 127
fi

exec "$jagt_bin" lint "$@"
