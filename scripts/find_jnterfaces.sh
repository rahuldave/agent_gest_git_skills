#!/usr/bin/env bash
# Print the folder of the jnterfaces clone that the checks use, or fail with a message that names each folder it tried.
#
#   find_jnterfaces.sh FILE    FILE is a file or folder that the clone must have, such as scripts/check_skill_links.py
#
# A folder is a jnterfaces clone when it has scripts/install_stack.py. The checks use the first clone of these:
#
# 1. $JNTERFACES_DIR, when it is set. Then no other folder.
# 2. The folder jnterfaces next to this repository.
# 3. The installed copy $SKILL_PACKAGES_DIR/jnterfaces, by default ~/.local/share/skill-packages/jnterfaces. The
#    installer of the gest_git_installer skill puts jnterfaces there.
# 4. A clone of the commit in scripts/jnterfaces_commit, the commit that CI tests, in
#    ${XDG_CACHE_HOME:-~/.cache}/agent_gest_git_skills/COMMIT/jnterfaces. The first use clones it from
#    $JNTERFACES_REPO, by default https://github.com/rahuldave/jnterfaces, so it needs the network once.
#
# The clone that is found must have FILE, or the script fails. It never goes on to the next clone, so all checks of one
# run use the same clone.
set -euo pipefail

file="${1:?usage: find_jnterfaces.sh FILE}"
repo_root="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
marker=scripts/install_stack.py

use() {
  local dir
  dir="$(CDPATH='' cd -- "$1" && pwd)"
  if [ ! -e "$dir/$file" ]; then
    echo "The jnterfaces clone at $dir has no $file. Update it, or set JNTERFACES_DIR to another clone." >&2
    exit 1
  fi
  printf '%s\n' "$dir"
  exit 0
}

if [ -n "${JNTERFACES_DIR:-}" ]; then
  [ -e "$JNTERFACES_DIR/$marker" ] && use "$JNTERFACES_DIR"
  echo "JNTERFACES_DIR names no jnterfaces clone: $JNTERFACES_DIR has no $marker." >&2
  exit 1
fi

home="${HOME:-}"
if [ -z "$home" ] && { [ -z "${SKILL_PACKAGES_DIR:-}" ] || [ -z "${XDG_CACHE_HOME:-}" ]; }; then
  echo "HOME is not set, so the installed copy and the cache have no folder. Set HOME, or set JNTERFACES_DIR." >&2
  exit 1
fi
tried=("$repo_root/../jnterfaces" "${SKILL_PACKAGES_DIR:-$home/.local/share/skill-packages}/jnterfaces")
for dir in "${tried[@]}"; do
  [ -e "$dir/$marker" ] && use "$dir"
done

pin="$(cat "$repo_root/scripts/jnterfaces_commit")"
cache="${XDG_CACHE_HOME:-$home/.cache}/agent_gest_git_skills/$pin/jnterfaces"
[ -e "$cache/$marker" ] && use "$cache"
if [ -e "$cache" ]; then
  echo "$cache is no jnterfaces clone: it has no $marker. Remove it, and run the check again." >&2
  exit 1
fi
repo="${JNTERFACES_REPO:-https://github.com/rahuldave/jnterfaces}"
echo "No jnterfaces clone in ${tried[*]}. Cloning $pin, the commit that CI tests, into $cache." >&2
mkdir -p "$(dirname "$cache")"
partial="$(mktemp -d "$(dirname "$cache")/partial.XXXXXX")"
trap 'rm -rf -- "$partial"' EXIT
# No prompt for a user name, so a wrong address fails and does not wait.
if ! GIT_TERMINAL_PROMPT=0 git clone --quiet --no-checkout "$repo" "$partial/jnterfaces" >&2 ||
   ! git -C "$partial/jnterfaces" checkout --quiet --detach "$pin" >&2; then
  echo "Could not clone $pin of $repo. Clone jnterfaces into one of ${tried[*]}, or set JNTERFACES_DIR." >&2
  exit 1
fi
# The rename is atomic, so another run sees the whole clone or none. It fails on a folder that another run renamed
# first, where mv would move the clone into that folder, and then the clone of the other run is used.
uv run --no-project --quiet python -c 'import os, sys; os.rename(sys.argv[1], sys.argv[2])' \
  "$partial/jnterfaces" "$cache" 2>/dev/null || [ -e "$cache/$marker" ] || {
  echo "Could not rename the new clone to $cache. Clone jnterfaces into one of ${tried[*]}, or set JNTERFACES_DIR." >&2
  exit 1
}
use "$cache"
