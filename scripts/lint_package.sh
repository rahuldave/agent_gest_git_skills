#!/usr/bin/env bash
# Check the package manifest and the bundled resources of each skill with lint_skill_bundle.py of
# agent_skill_package_maker, at the commit pinned below. It clones from GitHub. just check runs it, in CI too.
set -euo pipefail

package_maker_commit=6a5938c49ca71c374dc1a234a4d15134c484a741
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tool_root="$(mktemp -d)"
trap 'rm -rf -- "$tool_root"' EXIT
git clone --quiet https://github.com/rahuldave/agent_skill_package_maker.git "$tool_root/package-maker"
git -C "$tool_root/package-maker" checkout --quiet "$package_maker_commit"
cd "$repo_root"
uv run --no-project python "$tool_root/package-maker/skills/skill-package-maker/scripts/lint_skill_bundle.py" .
