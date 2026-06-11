#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/install.sh /path/to/target/repo

Install the Git/GitButler Gest agent skills, hooks, docs, templates, and graph
tool into a target repository. Existing AGENTS.md is preserved.
USAGE
}

if [ "$#" -ne 1 ]; then
  usage
  exit 64
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="$1"

check_required() {
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
  if ! command -v rsync >/dev/null 2>&1; then
    missing+=("rsync")
  fi
  if [ "${#missing[@]}" -gt 0 ]; then
    printf 'Missing required executable(s): %s\n' "${missing[*]}" >&2
    printf 'Install these before installing the Git/GitButler Gest skills. uv is required because skill-package-installer and Python setup profiles use uv-managed Python.\n' >&2
    exit 69
  fi
}

warn_optional() {
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

if [ ! -d "$target" ]; then
  echo "Target does not exist: $target" >&2
  exit 66
fi

check_required
warn_optional

mkdir -p "$target/.agents/skills" "$target/docs" "$target/tools" "$target/templates"
mkdir -p "$target/.claude/hooks" "$target/.codex/hooks"

rsync -a --delete "$repo_root/.agents/skills/" "$target/.agents/skills/"
rsync -a "$repo_root/.claude/hooks/" "$target/.claude/hooks/"
rsync -a "$repo_root/.codex/hooks/" "$target/.codex/hooks/"
rsync -a "$repo_root/.claude/settings.json" "$target/.claude/settings.json"
rsync -a "$repo_root/.codex/hooks.json" "$target/.codex/hooks.json"
rsync -a "$repo_root/docs/" "$target/docs/"
rsync -a --delete "$repo_root/templates/" "$target/templates/"
rsync -a "$repo_root/tools/gest_mermaid_graph.py" "$target/tools/gest_mermaid_graph.py"
chmod +x "$target/tools/gest_mermaid_graph.py"

if [ ! -f "$target/AGENTS.md" ]; then
  cp "$repo_root/AGENTS.template.md" "$target/AGENTS.md"
else
  echo "Kept existing AGENTS.md; merge AGENTS.template.md manually if needed." >&2
fi

echo "Installed Git/GitButler Gest agent skills into $target"
echo "Review AGENTS.md, .claude/settings.json, and .codex/hooks.json before use."
