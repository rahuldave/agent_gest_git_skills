#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${1:-all}"

required_files=(
  "README.md"
  "AGENTS.template.md"
  "AGENTS.starter.md"
  "AGENTS.instructions.md"
  "CLAUDE.md"
  "Justfile"
  "skill-package.json"
  ".claude/settings.json"
  ".codex/hooks.json"
  "docs/README.md"
  "docs/TUTORIAL.md"
  "docs/gest_codex_workflow.md"
  "docs/integration_delivery_workflow.md"
  "docs/tag_dependency_workflow.md"
  "docs/protocol_flows.md"
  "notes/live_protocol_flow_transcript_2026-06-14.md"
  "docs/g_commands_cheatsheet.md"
  "docs/just_command_contract.md"
  "docs/agent_task_draft_workflow.md"
  "docs/live_agent_result_recursive_lab.md"
  "scripts/run_stack_rebase_lab.sh"
  "scripts/run_tag_dependency_agent_dry_run.sh"
  "scripts/run_tag_dependency_typescript_lab.sh"
  "scripts/run_language_profile_labs.sh"
  "scripts/run_cx_examples_lab.sh"
  "scripts/run_agentic_target_lab.sh"
  "scripts/run_agent_result_lab.sh"
  "scripts/run_agent_task_draft_lab.sh"
  "scripts/run_agent_result_recursive_live_lab.sh"
  "scripts/jagt_lint_agent_task.sh"
  "scripts/jagt_lint_agent_task_draft.sh"
  "scripts/jagt_lint_agent_result.sh"
  "scripts/validate_agent_task.sh"
  "scripts/validate_agent_task_draft.sh"
  "scripts/validate_agent_result.sh"
  "fixtures/agent_task_draft/valid/result_pair.agent-task-draft.txt"
  "fixtures/agent_task_draft/invalid/malformed.agent-task-draft.txt"
  "fixtures/agent_task_draft/invalid/missing_approval.agent-task-draft.txt"
  "fixtures/agent_task_draft/invalid/missing_safety_language.agent-task-draft.txt"
  "fixtures/agent_task_draft/invalid/mode_agentic.agent-task-draft.txt"
  "fixtures/agent_task_draft/invalid/overbroad_allowed_actions.agent-task-draft.txt"
  "fixtures/agent_task_draft/invalid/direct_execution.agent-task-draft.txt"
  "fixtures/agent_task_draft/fresh_context/AGENTS.md"
  ".agents/skills/gest_git_installer/SKILL.md"
  ".agents/skills/gest_git_installer/scripts/install_gest_git_package.sh"
  ".agents/skills/gtw/scripts/worktree.py"
  ".agents/just/roles/agent_gest_git_skills.just"
  "templates/README.md"
)

for file in "${required_files[@]}"; do
  if [ ! -f "$repo_root/$file" ]; then
    echo "missing required file: $file" >&2
    exit 1
  fi
done

# Canonical public guidance must match each installed skill copy byte for byte.
check_mirror() {
  local source="$1" mirror="$2"
  [ -f "$repo_root/$source" ] || { echo "missing canonical file: $source" >&2; exit 1; }
  [ -f "$repo_root/$mirror" ] || { echo "missing mirror file: $mirror" >&2; exit 1; }
  cmp -s "$repo_root/$source" "$repo_root/$mirror" || {
    echo "stale mirror: $mirror differs from $source" >&2
    exit 1
  }
}
check_mirror "AGENTS.template.md" ".agents/skills/gsu/assets/templates/AGENTS.template.md"
# The starter and the rules that just install writes as the parts of the role are the two halves of the template.
uv run --no-project --quiet python "$repo_root/scripts/split_agents_template.py" --check
check_mirror "docs/gest_codex_workflow.md" ".agents/skills/gtw/references/gest_codex_workflow.md"
for skill in gor gtw gpl gcm gpa gpr grv gsu gte; do
  check_mirror "docs/integration_delivery_workflow.md" ".agents/skills/$skill/references/integration_delivery_workflow.md"
done
check_mirror "templates/README.md" ".agents/skills/gsu/assets/templates/README.md"
for name in tag_dependency_workflow live_agent_result_recursive_lab; do
  for mirror in "$repo_root"/.agents/skills/*/references/"$name.md"; do
    check_mirror "docs/$name.md" "${mirror#"$repo_root/"}"
  done
done

for skill in gbs gcm gdo gfm gest_git_installer gim gis gor gpa gpl gpr grv gsp gsu gte gtw; do
  if [ ! -f "$repo_root/.agents/skills/$skill/SKILL.md" ]; then
    echo "missing g skill: $skill" >&2
    exit 1
  fi
  # Installed copies carry the licence in the front matter, because no installer copies LICENSE.
  if ! awk 'NR==1 && $0!="---" {exit 1} NR>1 && $0=="---" {exit found ? 0 : 1} NR>1 && /^license: MIT, copyright \(c\) 2026 Rahul Dave\. .*rahuldave\/agent_gest_git_skills$/ {found=1}' "$repo_root/.agents/skills/$skill/SKILL.md"; then
    echo "$skill/SKILL.md front matter has no MIT license line" >&2
    exit 1
  fi
done
grep -q '^MIT License$' "$repo_root/LICENSE" || { echo "LICENSE is not the MIT licence" >&2; exit 1; }

while IFS= read -r script; do
  bash -n "$script"
done < <(find "$repo_root/scripts" "$repo_root/.agents/skills" "$repo_root/.claude/hooks" "$repo_root/.codex/hooks" -type f -name '*.sh' | sort)

# Python comes from uv, so the machine needs just and uv only.
python=(uv run --no-project --quiet python)
"${python[@]}" -m json.tool "$repo_root/.claude/settings.json" >/dev/null
"${python[@]}" -m json.tool "$repo_root/.codex/hooks.json" >/dev/null
"${python[@]}" -m json.tool "$repo_root/skill-package.json" >/dev/null

required_text=(
  "git rebase --update-refs"
  "gh pr create --base"
  "stacked PRs with plain git"
  "ordinary git branch PR"
  "ordinary git multi-commit PR"
  "physical git worktrees"
  "Tags And ast-grep Dependency Check"
  "Pull Request Command Map"
  "gh repo delete --yes"
  "Merge The Tutorial PRs"
  "PR acceptance checkpoint"
  "gh pr diff <number> --patch"
  "gh pr checks <number>"
  "gh pr merge <pr> --merge --match-head-commit <reviewed-head-sha>"
  "state MERGED"
  "existing-tags.txt"
  "new dynamic tags: none"
  "vocabulary source"
  "After the agent finishes, check:"
  "classification.tags.reviewed"
  "impact.ast_grep.required"
  "count-or-probability-coloring"
  "probability-pill-colors"
  "tag-dependency-dry-run"
  "tag-dependency-live-lab"
  "ast-grep run"
  "Live TypeScript Tag And ast-grep Dependency Lab"
  "tag dependency expansion"
  "ast-grep dependency expansion"
  "run_tag_dependency_typescript_lab.sh"
  "git worktree add"
  "run_language_profile_labs.sh"
  "language-profile-labs"
  "live local end-to-end"
  "cx Incremental Builds"
  "cx-examples-lab"
  "skill-package-maker"
  "skill-package.json"
  "uv --version"
  "rsync --version"
  "run_cx_examples_lab.sh"
  "agentic-target-lab"
  "run_agentic_target_lab.sh"
  "jagt_lint_agent_task.sh"
  "validate_agent_task.sh"
  "AGENT_TASK v1"
  "agent-result-lab"
  "agent-result-recursive-live-lab"
  "protocol-flow-labs"
  "run_agent_result_lab.sh"
  "run_agent_result_recursive_live_lab.sh"
  "jagt_lint_agent_result.sh"
  "validate_agent_result.sh"
  "AGENT_RESULT v1"
  "AGENT_RESULT is report-only"
  "agent-task-draft-lab"
  "run_agent_task_draft_lab.sh"
  "jagt_lint_agent_task_draft.sh"
  "validate_agent_task_draft.sh"
  "AGENT_TASK_DRAFT v1"
  "jagt draft lint"
  "legacy shell reference"
  "stochastic task proposals"
  "proposal, not executable"
  "approval.required: true"
  "jagt render"
  "jagt lint"
  "final_agent_task_lints"
  "fresh-context"
  "direct draft execution rejection"
  "expected target/status"
  "required file"
  "proposed_tasks"
  "parent-orchestrated"
  "local-recursion-supported"
  "Live AGENT_RESULT Recursive Lab"
  "two successive subagents"
  "planner subagent"
  "worker subagent"
  "unsafe proposal"
  "wc -w"
  "Subagent Execution Boundary"
  "Subagent Result Boundary"
  "Protocol Flow Labs"
  "Parent Agent Checklist"
  "Live Protocol Flow Transcript"
  "jagt draft lint"
  "validation failures"
  "subagent handoff"
  "subagent result"
  "hook-triggered packets"
  "agentic verification targets"
  "nested agentic Just calls"
  "agentic dependencies"
  "Artifact Pipeline"
  "Incremental C Build"
  "Python With UV"
  "TypeScript With NPM"
  "Rust With Cargo"
)

for needle in "${required_text[@]}"; do
  if ! grep -R "$needle" "$repo_root/AGENTS.template.md" "$repo_root/README.md" "$repo_root/docs" "$repo_root/.agents/skills" "$repo_root/scripts" >/dev/null; then
    echo "missing required workflow text: $needle" >&2
    exit 1
  fi
done

for stale_tutorial_text in "Latest Live Run" "422 Unprocessable Entity"; do
  if grep -q "$stale_tutorial_text" "$repo_root/docs/TUTORIAL.md"; then
    echo "stale run/debugging text remains in docs/TUTORIAL.md: $stale_tutorial_text" >&2
    exit 1
  fi
done

# The package dropped one version-control tool, and its hooks blocked plain git. No file may name that tool or its
# commands again. Only the specs, which describe the removal, and the historical notes may. The patterns are split,
# so that this script does not name the tool either.
tool='[g]it[-_[:space:]]*[b]utler'
# A command of the tool counts only where a command can stand, so "Tests pass, but update the docs" is plain
# English:
# - anywhere: in backticks, after a "$ " prompt, after "command -v", or as a "name" in JSON;
# - in code, which is each file that is not Markdown and each fenced block of a Markdown file: at the start of a
#   line or after ;, &, |, (, sudo, exec or run:, with a known subcommand or a flag.
# Global flags such as -j or --json can come before the subcommand. git grep -E on macOS has no \< or \>, so the
# word edges are spelled out.
flags='([[:space:]]+--?[[:alnum:]][[:alnum:]-]*)*'
subcommands='status|st|diff|show|log|branch|commit|push|pull|pr|stage|unstage|absorb|rub|oplog|undo|restore|mark|unmark|amend|apply|unapply|update|teardown|setup|init|base|worktree|config|describe|new|merge|squash|move|discard|resolve|reword|uncommit|forge|review|gui|help|completions|claude|mcp|skill|alias|lazy'
inline_command="\`[b]ut[[:space:]\`]|\\\$[[:space:]]+[b]ut([[:space:]]|\$)|-v[[:space:]]+[b]ut([^[:alnum:]_-]|\$)|\"name\"[[:space:]]*:[[:space:]]*\"[b]ut\""
position='(^|[;&|(]|(sudo|exec|run:)[[:space:]])[[:space:]]*'
code_command="${position}[b]ut${flags}[[:space:]]+(${subcommands})([^[:alnum:]_-]|\$)|${position}[b]ut[[:space:]]+--?[[:alnum:]]"
# fenced DIR: copies of the Markdown files of DIR, in a new folder, that keep only the lines of fenced blocks.
# The other lines become empty, so the line numbers stay.
fenced() {
  local dir="$1" out file
  out="$(mktemp -d)"
  while IFS= read -r -d '' file; do
    file="${file#./}"
    mkdir -p "$out/$(dirname "$file")"
    awk '/^[[:space:]]*(```|~~~)/ { fence = !fence; print ""; next } { print (fence ? $0 : "") }' \
      "$dir/$file" > "$out/$file"
  done < <(if [ -d "$dir/.git" ] || [ -f "$dir/.git" ]; then
             git -C "$dir" ls-files -z -co --exclude-standard -- '*.md' ':!docs/specs/' ':!notes/'
           else (cd "$dir" && find . -name '*.md' -print0); fi)
  printf '%s\n' "$out"
}
# hits DIR: the lines of DIR that name the tool or run one of its commands. In a repository, only the files that
# git tracks or would add count, outside docs/specs/ and notes/. git grep exits 1 when no line matches.
hits() {
  local dir="$1" index=(--untracked) code
  [ -d "$dir/.git" ] || [ -f "$dir/.git" ] || index=(--no-index)
  (cd "$dir" && git grep "${index[@]}" -nIiE -e "$tool" -- . ':!docs/specs/' ':!notes/') || [ $? -eq 1 ] || exit 1
  (cd "$dir" && git grep "${index[@]}" -nIE -e "$inline_command" -- . ':!docs/specs/' ':!notes/') || [ $? -eq 1 ] || exit 1
  (cd "$dir" && git grep "${index[@]}" -nIE -e "$code_command" -- . ':!*.md' ':!docs/specs/' ':!notes/') \
    || [ $? -eq 1 ] || exit 1
  code="$(fenced "$dir")"
  (cd "$code" && git grep --no-index -nIE -e "$code_command" -- .) || [ $? -eq 1 ] || { rm -rf -- "$code"; exit 1; }
  rm -rf -- "$code"
}
# The scan must find each positive sample and no negative one, or it could pass when it should fail. The samples
# split the words, so that this script does not match itself.
samples="$(mktemp -d)"
sample() {
  local want="$1" name="$2" line found
  shift 2
  for line in "$@"; do
    rm -rf -- "$samples/s"; mkdir "$samples/s"
    if [ "${name##*.}" = md ] && [ "$want" = fenced ]; then
      printf '```bash\n%s\n```\n' "$line" > "$samples/s/$name"
    else
      printf '%s\n' "$line" > "$samples/s/$name"
    fi
    found="$(hits "$samples/s")"
    if [ "$want" = none ] && [ -n "$found" ]; then
      echo "the scan matches the plain English line: $line" >&2; rm -rf -- "$samples"; exit 1
    elif [ "$want" != none ] && [ -z "$found" ]; then
      echo "the scan misses the sample line in $name: $line" >&2; rm -rf -- "$samples"; exit 1
    fi
  done
}
sample hit a.md 'Git''Butler' 'GIT''BUTLER' 'git''-butler' 'Git ''Butler' 'git''_butler' 'git  ''butler' \
  '`bu''t log`' '`bu''t -j status`' '$ bu''t status' 'run `bu''t push` now' 'command -v bu''t >/dev/null' \
  '"name": "bu''t"'
sample hit a.sh 'bu''t -j status' 'bu''t --json status' 'bu''t log' 'bu''t init' 'bu''t base update' \
  'bu''t worktree' 'bu''t restore' 'bu''t config' '    bu''t commit -m x' 'sudo bu''t status' 'x && bu''t status' \
  'y="$(bu''t status)"' 'exec bu''t commit' 'bu''t claude' 'bu''t mcp'
sample hit a.yml '  - run: bu''t push' '    run: bu''t status'
sample fenced a.md 'bu''t log' 'bu''t -j status' '  bu''t base update'
sample none a.md 'Tests pass, bu''t update the docs first.' 'It builds, bu''t push only after review.' \
  'Small, bu''t branch protection blocks it.' 'Fine bu''t status checks fail.' 'Not "bu''t" alone.' \
  'bu''t it does not simulate the agents.' 'bu''t update the docs.' 'bu''t status reports differ.' \
  'bu''t push back if needed.' 'bu''t commit to it.' 'bu''t new tests fail.' 'bu''t log the time later' \
  'bu''t -1 day' 'bu''t commits are fine' 'a butter knife' 'about pushes'
sample none a.sh '# Fine bu''t status checks fail.' 'echo "it builds, bu''t push later"'
rm -rf -- "$samples"
tool_hits="$(hits "$repo_root")"
if [ -n "$tool_hits" ]; then
  printf '%s\n' "$tool_hits" >&2
  echo "a file outside docs/specs/ and notes/ names the dropped version-control tool or one of its commands" >&2
  exit 1
fi

# Installed copies have no docs/ tree, so shipped guidance must not point into it.
shipped_text=("$repo_root/AGENTS.template.md" "$repo_root/AGENTS.starter.md" "$repo_root/AGENTS.instructions.md")
while IFS= read -r file; do shipped_text+=("$file"); done < <(
  find "$repo_root/.agents/skills" "$repo_root/.claude/hooks" "$repo_root/.codex/hooks" \
    -type f \( -name '*.md' -o -name '*.sh' -o -name '*.just' -o -name '*.yaml' -o -name '*.txt' \) | sort)
[ "${#shipped_text[@]}" -gt 1 ] || { echo "no shipped guidance files found" >&2; exit 1; }
refs="$(grep -hoE '\.agents/skills/[A-Za-z0-9_./-]+\.(md|sh|py)' "${shipped_text[@]}" | sort -u)" || [ $? -eq 1 ] || exit 1
while IFS= read -r ref; do
  [ -n "$ref" ] || continue
  skill="${ref#.agents/skills/}"; skill="${skill%%/*}"
  # References into other packages, such as skill-package-maker, are not shipped here.
  [ -d "$repo_root/.agents/skills/$skill" ] || continue
  [ -f "$repo_root/$ref" ] || { echo "shipped reference to missing file: $ref" >&2; exit 1; }
done <<< "$refs"
docs_hits="$(grep -nE '(^|[^/A-Za-z_])\.?/?docs/[A-Za-z0-9_./-]+\.md' "${shipped_text[@]}")" || [ $? -eq 1 ] || exit 1
if [ -n "$docs_hits" ]; then
  printf '%s\n' "$docs_hits" >&2
  echo "shipped guidance names a docs/ file that installed repositories do not have" >&2
  exit 1
fi

# A link to a skill of another package needs a fallback in the same paragraph, because a target may not have
# that skill. Each link into jnterfaces must name a path that jnterfaces ships. The checker lives in jnterfaces.
jnterfaces_dir="${JNTERFACES_DIR:-$repo_root/../jnterfaces}"
if [ ! -f "$jnterfaces_dir/scripts/check_skill_links.py" ]; then
  echo "The link check needs a jnterfaces clone with scripts/check_skill_links.py at $jnterfaces_dir. Clone https://github.com/rahuldave/jnterfaces there, or set JNTERFACES_DIR." >&2
  exit 1
fi
"${python[@]}" "$jnterfaces_dir/scripts/check_skill_links.py" --package "$repo_root" --resolve "$jnterfaces_dir" "${shipped_text[@]}"

# Shipped files must not carry paths from one machine.
path_hits="$(grep -rnE '/(Users|home)/[A-Za-z0-9._-]+/' "$repo_root/.agents/skills" "$repo_root/.claude" "$repo_root/.codex" "$repo_root/AGENTS.template.md" "$repo_root/templates")" || [ $? -eq 1 ] || exit 1
if [ -n "$path_hits" ]; then
  printf '%s\n' "$path_hits" >&2
  echo "shipped files contain a machine-specific absolute path" >&2
  exit 1
fi

# Only jnterfaces has an installer and the Justfile templates, so no copy may come back here.
for copy in scripts/install.sh scripts/install_package.py scripts/install_stack.sh templates/just .agents/skills/gsu/assets/templates/just; do
  if [ -e "$repo_root/$copy" ]; then
    echo "$copy is a copy of jnterfaces; use the jnterfaces installer and the templates of its just skill" >&2
    exit 1
  fi
done

# Exercise both hook payload formats in disposable plain and managed checkouts.
(
  cd "$repo_root"
  "${python[@]}" -m unittest scripts/test_raw_git_guards.py -q
  "${python[@]}" -m unittest scripts/test_worktrees.py -q
)

if [ "$mode" = "--diff" ]; then
  git -C "$repo_root" diff --check
fi

echo "repository checks passed"
