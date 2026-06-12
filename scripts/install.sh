#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/install.sh /path/to/target/repo

Install the Git/GitButler Gest agent skills, hooks/settings, and AGENTS starter
guidance into a target repository. Existing AGENTS.md is preserved.
USAGE
}

if [ "$#" -ne 1 ]; then
  usage
  exit 64
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="$1"

warn_missing_workflow_prereqs() {
  local missing=()
  if ! command -v git >/dev/null 2>&1; then
    missing+=("git")
  fi
  if ! command -v gest >/dev/null 2>&1; then
    missing+=("gest")
  fi
  if ! command -v just >/dev/null 2>&1; then
    missing+=("just")
  fi
  if ! command -v uv >/dev/null 2>&1; then
    missing+=("uv")
  fi
  if [ "${#missing[@]}" -gt 0 ]; then
    printf 'Missing workflow executable(s): %s\n' "${missing[*]}" >&2
    printf 'Installing the skills anyway. Install these before running the Git/GitButler Gest workflow. uv is required by Python setup profiles and package authoring checks.\n' >&2
  fi
}

warn_optional() {
  if ! command -v rsync >/dev/null 2>&1; then
    printf 'Optional executable not found: rsync; using cp fallback for installation.\n' >&2
  fi
  if ! command -v gh >/dev/null 2>&1; then
    printf 'Optional executable not found: gh\n' >&2
  fi
  if ! command -v but >/dev/null 2>&1; then
    printf 'Optional executable not found: but\n' >&2
  fi
  if ! command -v ast-grep >/dev/null 2>&1; then
    printf 'Optional executable not found: ast-grep\n' >&2
  fi
  if ! command -v direnv >/dev/null 2>&1; then
    printf 'Optional executable not found: direnv\n' >&2
  fi
  if ! command -v cx >/dev/null 2>&1; then
    printf 'Optional executable not found: cx\n' >&2
  fi
}

copy_dir_delete() {
  local src="$1"
  local dest="$2"
  mkdir -p "$dest"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "$src/" "$dest/"
  else
    cp -R "$src/." "$dest/"
  fi
}

copy_dir_merge() {
  local src="$1"
  local dest="$2"
  mkdir -p "$dest"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a "$src/" "$dest/"
  else
    cp -R "$src/." "$dest/"
  fi
}

copy_file() {
  local src="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a "$src" "$dest"
  else
    cp "$src" "$dest"
  fi
}

if [ ! -d "$target" ]; then
  echo "Target does not exist: $target" >&2
  exit 66
fi

warn_missing_workflow_prereqs
warn_optional

mkdir -p "$target/.agents/skills"
mkdir -p "$target/.claude/hooks" "$target/.codex/hooks"

for source_skill in "$repo_root"/.agents/skills/*; do
  [ -d "$source_skill" ] || continue
  skill_name="$(basename "$source_skill")"
  copy_dir_delete "$source_skill" "$target/.agents/skills/$skill_name"
done
copy_dir_merge "$repo_root/.claude/hooks" "$target/.claude/hooks"
copy_dir_merge "$repo_root/.codex/hooks" "$target/.codex/hooks"
copy_file "$repo_root/.claude/settings.json" "$target/.claude/settings.json"
copy_file "$repo_root/.codex/hooks.json" "$target/.codex/hooks.json"

if [ ! -f "$target/AGENTS.md" ]; then
  cp "$repo_root/AGENTS.template.md" "$target/AGENTS.md"
else
  echo "Kept existing AGENTS.md; merge AGENTS.template.md manually if needed." >&2
fi

echo "Installed Git/GitButler Gest agent skills into $target"
echo "Review AGENTS.md, .claude/settings.json, and .codex/hooks.json before use."
