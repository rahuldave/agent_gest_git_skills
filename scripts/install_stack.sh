#!/usr/bin/env bash
# Install agent_gest_git_skills, jnterfaces and, with --with-lanes, sklanes into one target repository.
# Each package runs its own installer, so each records its own source revision in .agents/<package>-install.json.
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/install_stack.sh [OPTIONS] [--] TARGET

Options: [--with-lanes] [--jnterfaces DIR] [--sklanes DIR] [--clean] [--dry-run]

Install the Gest g* skills, the jnterfaces skills (just, jagt-protocol, cx) and,
with --with-lanes, the sklanes skill (lanes) into TARGET.

  --jnterfaces DIR  clone of jnterfaces; default: ../jnterfaces next to this repository
  --sklanes DIR     clone of sklanes; default: ../sklanes next to this repository
  --clean           install the committed HEAD of each clone, without uncommitted changes
  --dry-run         check every package and write nothing

All packages are checked with a dry run before any package writes a file.
USAGE
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
jnterfaces="$repo_root/../jnterfaces"
sklanes="$repo_root/../sklanes"
target=""
with_lanes=0
clean=0
dry_run=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --with-lanes) with_lanes=1 ;;
    --clean) clean=1 ;;
    --dry-run) dry_run=1 ;;
    --jnterfaces) [ "$#" -ge 2 ] || { usage; exit 2; }; jnterfaces="$2"; shift ;;
    --sklanes) [ "$#" -ge 2 ] || { usage; exit 2; }; sklanes="$2"; shift ;;
    --) shift; [ "$#" -eq 1 ] && [ -z "$target" ] || { usage; exit 2; }; target="$1"; break ;;
    -*) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    *) [ -z "$target" ] || { echo "Only one TARGET is allowed" >&2; exit 2; }; target="$1" ;;
  esac
  shift
done
[ -n "$target" ] || { usage; exit 2; }
# An absolute path keeps a target such as -odd from looking like an option to an installer.
target="$(cd -- "$target" && pwd)" || { echo "Target does not exist" >&2; exit 2; }

# Check that DIR is a clone of the named package, then print its absolute path.
package_dir() {
  local dir="$1" name="$2"
  if [ ! -f "$dir/skill-package.json" ] || [ ! -x "$dir/scripts/install.sh" ]; then
    echo "No $name clone at $dir. Clone https://github.com/rahuldave/$name there, or pass --$name DIR." >&2
    return 1
  fi
  if ! python3 -c 'import json, sys; sys.exit(json.load(open(sys.argv[1]))["repository"]["name"] != sys.argv[2])' \
      "$dir/skill-package.json" "$name"; then
    echo "$dir is not the $name package." >&2
    return 1
  fi
  (cd "$dir" && pwd)
}

packages=("$repo_root")
packages+=("$(package_dir "$jnterfaces" jnterfaces)")
if [ "$with_lanes" -eq 1 ]; then
  packages+=("$(package_dir "$sklanes" sklanes)")
fi

install_one() {
  local dir="$1"; shift
  local options=("$@")
  if [ "$clean" -eq 1 ]; then
    options+=(--source-commit "$(git -C "$dir" rev-parse HEAD)")
  fi
  bash "$dir/scripts/install.sh" ${options[@]+"${options[@]}"} "$target"
}

for dir in "${packages[@]}"; do
  install_one "$dir" --dry-run
done
if [ "$dry_run" -eq 1 ]; then
  exit 0
fi
for dir in "${packages[@]}"; do
  install_one "$dir"
done

echo "Installed packages and their recorded source revisions:"
for record in "$target"/.agents/*-install.json; do
  printf '  %s: %s\n' "$(basename "$record")" \
    "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("source_revision"))' "$record")"
done
