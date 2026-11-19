#!/usr/bin/env bash
# Run the link checker of jnterfaces on the shipped files FILE..., as just lint does. A link to a skill of another
# package needs a fallback in the same paragraph, because a target may not have that skill. Each link into
# jnterfaces must name a path that jnterfaces ships. scripts/find_jnterfaces.sh finds the jnterfaces clone.
#
#   check_skill_links.sh FILE...
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ "$#" -gt 0 ] || { echo "usage: check_skill_links.sh FILE..." >&2; exit 2; }
jnterfaces_dir="$("$repo_root/scripts/find_jnterfaces.sh" scripts/check_skill_links.py)"
"$repo_root/scripts/warn_jnterfaces_pin.sh" "$jnterfaces_dir"
uv run --no-project --quiet python "$jnterfaces_dir/scripts/check_skill_links.py" --package "$repo_root" \
  --resolve "$jnterfaces_dir" "$@"
