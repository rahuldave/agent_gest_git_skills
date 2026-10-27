#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
missing=()
if ! command -v git >/dev/null 2>&1; then missing+=(git); fi
if ! command -v gest >/dev/null 2>&1; then missing+=(gest); fi
if ! command -v just >/dev/null 2>&1; then missing+=(just); fi
if ! command -v uv >/dev/null 2>&1; then missing+=(uv); fi
if [ "${#missing[@]}" -gt 0 ]; then
  printf 'Missing workflow executable(s): %s\n' "${missing[*]}" >&2
  printf 'Install these before running the Git/GitButler Gest workflow.\n' >&2
fi
optional=()
if ! command -v rsync >/dev/null 2>&1; then optional+=(rsync); fi
if ! command -v gh >/dev/null 2>&1; then optional+=(gh); fi
if ! command -v but >/dev/null 2>&1; then optional+=(but); fi
if ! command -v ast-grep >/dev/null 2>&1; then optional+=(ast-grep); fi
if ! command -v direnv >/dev/null 2>&1; then optional+=(direnv); fi
if ! command -v cx >/dev/null 2>&1; then optional+=(cx); fi
if [ "${#optional[@]}" -gt 0 ]; then
  printf 'Optional executable(s) not found: %s\n' "${optional[*]}" >&2
fi
exec python3 "$repo_root/scripts/install_package.py" --source "$repo_root" "$@"
