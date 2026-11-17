#!/usr/bin/env bash
# Warn when the jnterfaces clone in DIR is not the one that CI tests: another commit than PIN, or changes that are not
# committed. Then a check here can pass where CI fails, or fail where CI passes. It only warns, and it always exits 0.
#
#   warn_jnterfaces_pin.sh DIR [PIN]    PIN is the commit in scripts/jnterfaces_commit by default
set -uo pipefail

dir="$1"
pin="${2:-$(cat "$(dirname "${BASH_SOURCE[0]}")/jnterfaces_commit")}"
head="$(git -C "$dir" rev-parse HEAD 2>/dev/null)"
if [ "$head" != "$pin" ]; then
  echo "warning: the jnterfaces clone at $dir is not at $pin, the commit that CI tests" >&2
elif [ -n "$(git -C "$dir" status --porcelain 2>/dev/null)" ]; then
  echo "warning: the jnterfaces clone at $dir has changes that are not committed, and CI tests $pin without them" >&2
fi
exit 0
