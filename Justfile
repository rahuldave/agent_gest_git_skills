setup:
  @echo "No repository-local dependencies to install. Ensure git, gest, jagt, just, uv, rsync, and optional gh, ast-grep, direnv, cx are available."

lint:
  scripts/check_repo.sh

static: lint

test:
  scripts/run_stack_rebase_lab.sh
  scripts/run_tag_dependency_agent_dry_run.sh
  scripts/run_tag_dependency_typescript_lab.sh
  scripts/run_language_profile_labs.sh
  scripts/run_cx_examples_lab.sh
  scripts/run_agentic_target_lab.sh
  scripts/run_agent_result_lab.sh
  scripts/run_agent_task_draft_lab.sh

stack-rebase-lab:
  scripts/run_stack_rebase_lab.sh

tag-dependency-dry-run:
  scripts/run_tag_dependency_agent_dry_run.sh

tag-dependency-live-lab:
  scripts/run_tag_dependency_typescript_lab.sh

language-profile-labs:
  scripts/run_language_profile_labs.sh

cx-examples-lab:
  scripts/run_cx_examples_lab.sh

agentic-target-lab:
  scripts/run_agentic_target_lab.sh

agent-result-lab:
  scripts/run_agent_result_lab.sh

agent-task-draft-lab:
  scripts/run_agent_task_draft_lab.sh

agent-result-recursive-live-lab TRANSCRIPT_DIR:
  scripts/run_agent_result_recursive_live_lab.sh "{{TRANSCRIPT_DIR}}"

protocol-flow-labs: agentic-target-lab agent-result-lab agent-task-draft-lab

# Install this package into a scratch repository with the installer of a jnterfaces clone, and check the result.
# scripts/find_jnterfaces.sh finds the clone
install-test:
  #!/usr/bin/env bash
  set -euo pipefail
  jnterfaces="$(scripts/find_jnterfaces.sh scripts/install_stack.py)"
  scripts/warn_jnterfaces_pin.sh "$jnterfaces"
  target="$(mktemp -d)"; trap 'rm -rf -- "$target"' EXIT
  git -C "$target" init -q
  printf '{"model": "mine", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine.sh"}]}]}}\n' > "$target/x.json"
  mkdir -p "$target/.claude" && mv "$target/x.json" "$target/.claude/settings.json"
  install() { uv run --quiet --script "$jnterfaces/scripts/install_stack.py" --target "$target" --clone "agent_gest_git_skills=$PWD" "$@"; }
  install --defaults --without prose tasker
  fail() { echo "install-test: $*" >&2; exit 1; }
  for file in .agents/skills/gtw/SKILL.md .agents/skills/just/SKILL.md .claude/hooks/session-start.sh .codex/hooks/session-start.sh AGENTS.md .agents/gest-git-install.json; do
    test -f "$target/$file" || fail "missing $file after the install"
  done
  grep -q '"mine.sh"' "$target/.claude/settings.json" || fail "the install dropped the hook of the user"
  grep -q 'session-start' "$target/.claude/settings.json" || fail "the install merged no Claude hook"
  grep -q 'session-start' "$target/.codex/hooks.json" || fail "the install merged no Codex hook"
  grep -qxF 'Read and follow @.agents/instructions/tasker.md' "$target/AGENTS.md" || fail "AGENTS.md has no pointer to the rules"
  grep -qxF '@AGENTS.md' "$target/CLAUDE.md" || fail "CLAUDE.md does not import AGENTS.md"
  grep -q 'Project name:' "$target/AGENTS.md" || fail "AGENTS.md has no starter"
  cmp -s AGENTS.instructions.md "$target/.agents/instructions/tasker.md" || fail "the rules are not in .agents/instructions/tasker.md"
  # Claude Code imports the rules through CLAUDE.md and AGENTS.md, so its hook prints them only without the import.
  claude() {
    local out
    out="$(cd "$target" && CLAUDE_PROJECT_DIR="$target" .claude/hooks/session-start.sh)" || fail "the Claude hook failed"
    printf '%s' "$out" | uv run --no-project --quiet python -c 'import json, sys; print(json.load(sys.stdin)["hookSpecificOutput"]["additionalContext"])' || fail "the Claude hook printed no JSON"
  }
  out="$(claude)"
  if grep -q 'Branches And Review' <<<"$out"; then fail "the Claude hook prints the rules that Claude Code imports"; fi
  mv "$target/CLAUDE.md" "$target/CLAUDE.md.off"
  out="$(claude)"
  grep -q 'Branches And Review' <<<"$out" || fail "the Claude hook does not print the rules without the import"
  grep -q 'Branches And Review' <(cd "$target" && .codex/hooks/session-start.sh) || fail "the Codex hook does not print the rules"
  for hook in .claude/hooks/session-start.sh .codex/hooks/session-start.sh; do
    (cd "$target" && CLAUDE_PROJECT_DIR="$target" "$hook") | uv run --no-project --quiet python -c 'import json, sys; text = json.load(sys.stdin)["hookSpecificOutput"]["additionalContext"]; sys.exit(not text.startswith("Read all of .agents/instructions/tasker.md"))' || fail "$hook does not start with the line that asks for the whole rules file"
  done
  mv "$target/CLAUDE.md.off" "$target/CLAUDE.md"
  test -f "$target/.agents/just/roles/agent_gest_git_skills.just" || fail "missing the role recipes after the install"
  # The CI job runs just ci with the whole history, and the starter is a valid workflow.
  ci="$target/.github/workflows/check.yml"
  cmp -s .agents/skills/gsu/assets/templates/github-check.yml "$ci" || fail "the install wrote no CI starter"
  uv run --no-project --quiet --with pyyaml==6.0.2 python -c 'import sys, yaml; job = yaml.safe_load(open(sys.argv[1]))["jobs"]["ci"]; steps = job["steps"]; assert steps[0]["with"]["fetch-depth"] == 0; assert steps[-1]["run"] == "just ci"' "$ci" || fail "the CI starter does not run just ci with fetch-depth 0"
  just --justfile "$target/Justfile" --summary | tr ' ' '\n' | grep -qx ci || fail "the CI starter runs just ci, and the project has no ci recipe"
  just --justfile "$target/Justfile" --summary | tr ' ' '\n' | grep -qx ci-gate || fail "the project has no ci-gate recipe of the tasker role"
  # The release starter runs just check on a push to main, then just release with write access, and no agent.
  release="$target/.github/workflows/release.yml"
  cmp -s .agents/skills/gsu/assets/templates/github-release.yml "$release" || fail "the install wrote no release starter"
  uv run --no-project --quiet --with pyyaml==6.0.2 python -c 'import sys, yaml; flow = yaml.safe_load(open(sys.argv[1])); jobs = flow["jobs"]; assert flow[True]["push"]["branches"] == ["main"]; assert jobs["check"]["steps"][-1]["run"] == "just check"; job = jobs["release"]; assert job["needs"] == "check"; assert job["permissions"] == {"contents": "write"}; assert job["steps"][0]["with"]["fetch-depth"] == 0; assert job["steps"][-1]["run"] == "just release"' "$release" || fail "the release starter does not run just release after just check"
  for recipe in check release; do
    just --justfile "$target/Justfile" --summary | tr ' ' '\n' | grep -qx "$recipe" || fail "the release starter runs just $recipe, and the project has no $recipe recipe"
  done
  git -C "$target" -c user.name=t -c user.email=t@example.com commit -q --allow-empty --no-verify -m "docs: start"
  (cd "$target" && just release --dry-run) | grep -qx 'next tag: v0.1.0 (no tag yet)' || fail "just release --dry-run does not give v0.1.0 in a new project"
  (cd "$target" && just release-check) | grep -q 'release-check: no release tag in this checkout' || fail "just release-check does not pass in a new project"
  printf '# mine\n' > "$ci"
  [ "$(just --justfile "$target/Justfile" tasker-mode)" = git ] || fail "just tasker-mode does not print git"
  just --justfile "$target/Justfile" worktrees > /dev/null || fail "just worktrees failed"
  # The old hooks blocked plain git on the branch of the old workspace, so the check runs there.
  branch="$(git -C "$target" symbolic-ref HEAD)"
  git -C "$target" symbolic-ref HEAD "refs/heads/git""butler/workspace"
  for hook in .claude/hooks/raw-git-write-guard.sh .codex/hooks/raw-git-write-guard.sh; do
    out="$(cd "$target" && printf '%s' '{"tool_input": {"command": "git commit -m x", "cmd": "git commit -m x"}}' | CLAUDE_PROJECT_DIR="$target" "$hook")" || fail "$hook failed"
    if grep -q permissionDecision <<<"$out"; then fail "$hook blocks a plain git commit"; fi
  done
  git -C "$target" symbolic-ref HEAD "$branch"
  install tasker=gitwt
  [ "$(just --justfile "$target/Justfile" tasker-mode)" = gitwt ] || fail "just tasker-mode does not print gitwt"
  install --without tasker
  for gone in .agents/skills/gtw .claude/hooks .codex .agents/gest-git-install.json .agents/just/roles/agent_gest_git_skills.just; do
    if [ -e "$target/$gone" ]; then fail "$gone is still there after the removal"; fi
  done
  grep -q '"mine.sh"' "$target/.claude/settings.json" || fail "the removal dropped the hook of the user"
  [ "$(cat "$target/.github/workflows/check.yml")" = '# mine' ] || fail "a reinstall or the removal changed the CI file of the user"
  test ! -e "$target/.agents/instructions/tasker.md" || fail "the rules are still there after the removal"
  if grep -q 'instructions/tasker.md' "$target/AGENTS.md"; then fail "the removal left the pointer in AGENTS.md"; fi
  if grep -q 'session-start' "$target/.claude/settings.json"; then fail "the removal left a Gest hook"; fi
  # The removal keeps a CI starter that nobody edited, because the starter is the project's from the start.
  rm -f "$target/.github/workflows/check.yml"
  install --defaults --without prose tasker
  install --without tasker
  cmp -s .agents/skills/gsu/assets/templates/github-check.yml "$target/.github/workflows/check.yml" || fail "the removal took out the CI starter"
  echo "install-test: install and removal passed"

# Everything a commit must pass, and each check that CI runs: the release version, the lint, the manifest, the labs, the install, the source archive, the docs site and the diff
check: release-check lint package-lint stack-rebase-lab install-test source-archive docs-check diff-check

# The release tags, with release_tag.py of the skill gpa. The job release of verify.yml runs just release on each push to main.
release_tag := "uv run --no-project --quiet --no-python-downloads --python '>=3.9' python .agents/skills/gpa/scripts/release_tag.py"

# Tag HEAD with the next release vX.Y.Z by semver, push the tag and check it. Takes --dry-run first
[positional-arguments]
release *args:
  @{{release_tag}} "$@"

# Print the next tag, or fail on a git error. It needs no network and no remote
release-check:
  {{release_tag}} --check

# Build the source archive of HEAD into dist/, and check that it holds the manifest and the installer skill
source-archive:
  #!/usr/bin/env bash
  set -euo pipefail
  name=agent_gest_git_skills-source.tar.gz
  mkdir -p dist
  git archive --format=tar.gz --prefix=agent_gest_git_skills/ -o "dist/$name" HEAD
  listing="$(tar -tzf "dist/$name")"
  for file in skill-package.json .agents/skills/gest_git_installer/SKILL.md; do
    grep -Fxq "agent_gest_git_skills/$file" <<<"$listing" || { echo "source-archive: dist/$name has no $file" >&2; exit 1; }
  done
  # shasum is on macOS and on the Ubuntu runner, and sha256sum is not on macOS before 14.
  (cd dist && shasum -a 256 "$name" > SHA256SUMS && shasum -a 256 -c SHA256SUMS)

# Check the package manifest and the bundled resources of each skill, as CI does
package-lint:
  scripts/lint_package.sh

# Check the changes that are not committed for whitespace errors and conflict markers
diff-check:
  git diff --check

verify: lint test diff-check

# The documentation site, from docs/, with smalldocs.
smalldocs := "uvx --quiet smalldocs@0.5.12"

docs-check:
  {{smalldocs}} check docs

docs:
  {{smalldocs}} preview docs

docs-build:
  {{smalldocs}} render docs --strict

# Build the site in strict mode, then push it to the branch gh-pages
docs-publish: docs-build
  {{smalldocs}} publish gh-pages docs --no-render
