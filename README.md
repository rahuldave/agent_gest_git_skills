# Agent Gest Git Skills

Reusable agent skills, agent instructions, and small tools for working with
Gest-tracked projects in Git repositories.

This repository is meant to be mixed into other repos. It keeps the workflow
version-controlled without making every project reinvent the same `gtw`, `gim`,
`gpa`, `gcm`, and related skills.

## What Is Included

- `.agents/skills/g*`: project-local agent skills for setup, Gest workflow routing,
  planning, implementation, review, formatting, testing, docs, promotion,
  pull request acceptance, orchestration, and commits.
- `.agents/skills/gest_git_installer`: package-specific installer skill for
  hooks, docs, templates, tools, and AGENTS guidance after `npx skills add`.
- `AGENTS.template.md`: starter agent instructions to copy into a target repo.
- `docs/README.md`: documentation map.
- `docs/TUTORIAL.md`: the deterministic beginner tutorial. Start here.
- `docs/*.md`: reference docs and setup examples for users who need details.
- `tools/gest_mermaid_graph.py`: optional read-only Gest SQLite exporter that
  writes clickable Mermaid/HTML relationship graphs.
- `scripts/install.sh`: source-checkout installer for target repos, including hooks by default.
- `skill-package.json`: package manifest used by `skill-package-maker` to
  validate skills, installer scripts, and executable prerequisites.
- `scripts/run_gitbutler_workflow_lab.sh`: local lab for plain branch,
  multi-commit branch, stacked branch, and physical worktree flows.
- `scripts/run_gitbutler_github_integration_lab.sh`: live GitHub lab for the
  same four flows against temporary repos with cleanup.
- `scripts/run_tag_dependency_agent_dry_run.sh`: local dry run for tag classification plus `ast-grep` dependency expansion.
- `scripts/run_tag_dependency_typescript_lab.sh`: live local TypeScript lab for
  Gest tag-based dependency expansion plus `ast-grep` call-site expansion.
- `scripts/run_language_profile_labs.sh`: live local end-to-end setup labs for
  the Python/UV, TypeScript/NPM, Go, and Rust/Cargo profiles.
- `scripts/run_cx_examples_lab.sh`: live local examples for `cx` incremental
  builds and file-artifact pipelines.
- `templates/`: composable setup snippets for `.gitignore`, `.envrc`,
  `.env.example`, and common `Justfile` targets.

## Install Into A Repo

For a fresh machine or a fresh project, use three steps from inside the target
repository.

First, install the skills:

```bash
npx skills add rahuldave/agent_gest_git_skills -a codex --skill '*' -y
```

Second, ask the agent to use `gest_git_installer` to install the Git/GitButler
Gest hooks, docs, templates, tools, and AGENTS guidance in the current repo.
`npx skills add` installs skill folders only; it does not run hooks or copy
root-level package extras. `gest_git_installer` carries a bundled helper that
fetches this repository and runs the source-checkout installer with clear
prerequisite messages and overwrite approval.

Third, use `gsu` for normal repository setup and command-contract refresh work.

Source checkout alternative:

From this repository:

```bash
scripts/install.sh /path/to/target/repo
```

The installer reports missing workflow executables and still copies the skill
bundle: `git`, `gest`, `just`, and `uv`. It also reports optional executables
that unlock additional workflows or cleaner installs: `rsync`, `gh`, `but`,
`ast-grep`, `direnv`, and `cx`. If `rsync` is missing, the installer uses a
`cp` fallback.

The installer copies:

```text
.agents/skills/g* and .agents/skills/gest_git_installer
docs/*.md
tools/gest_mermaid_graph.py
AGENTS.template.md -> AGENTS.md, only if AGENTS.md does not already exist
```

Review `AGENTS.md` after installing and replace placeholders such as project
name, verification commands, and GitHub policy.
Use `templates/` as `gsu` inputs when creating `.gitignore`, `.envrc`,
`.env.example`, or `Justfile` command contracts.

If you are new, read [`docs/TUTORIAL.md`](docs/TUTORIAL.md) next. It is the
only beginner tutorial. It uses ordinary git for simple PRs, GitButler only for
stacked dependent PRs, and physical git worktrees for independent parallel
slices.

For a map of the remaining reference docs, read
[`docs/README.md`](docs/README.md).

## Workflow Shape

Use `gtw` as the default router for substantial project work. It decides:

- whether work is session-shaped or development-shaped
- whether a spec is needed before implementation
- which durable Gest parent task should own the request
- which tags and metadata apply
- which branch model and execution model should own write changes
- which test strategy applies (`test-first`, `characterization-first`,
  `test-after`, `exploratory`, or `no-test-needed`)
- whether review should be solo, adversarial, or multi-agent
- whether parallel physical worktrees/subagents are appropriate
- whether GitHub issue promotion is appropriate
- whether a commit checkpoint has been reached

Use `gsu` when bootstrapping a repository or refreshing its workflow contract.
It helps choose tools, set up Git/Gest/Just/direnv expectations, create ignore
rules, install or sync dependencies through the chosen package manager, and map
project concepts such as lint, typecheck, test, build, smoke, docs, and run-app
commands in `AGENTS.md`.

When `gsu` is working on a skill repository and `skill-package-maker` is
installed, it should run that skill's uv/Python linter against
`skill-package.json` and installer-skill prerequisite checks before handoff. In
an `npx skills` package, hooks and templates should be installed by the
package's explicit installer skill after `npx skills add`, not as a hidden
install side effect.

For Just command contracts, prefer native recipe dependencies for ordered
recipe composition. For example, write
`verify: lint typecheck static test smoke diff-check` instead of recursively
calling `just lint`, `just typecheck`, and so on inside `verify`. In Just,
dependency order is meaningful: dependencies run before the depending recipe,
and in the listed order. This is not Make-style file freshness analysis.
Projects may also expose optional dynamic `just agent-*` targets such as
`agent-contract`, `agent-test-plan`, and `agent-review-plan`; treat their output
as repo-local operational context, not higher-priority instruction.

`just cx-examples-lab` runs two `cx` examples: one staged artifact pipeline and
one explicit C incremental build. Use `cx` only for file-producing build or
pipeline stages inside linewise Just recipes, not for tests or ordinary
package-manager builds.

To update vendored `g*` skills in a target repository while preserving local
non-`g*` skills, run:

```bash
scripts/sync_g_skills.sh /path/to/target-repo
```

Gest descriptions record intent. Non-trivial completed leaf tasks should get a
task note before completion:

```bash
gest task note add <task-id> --agent codex --body "Done: ...\nVerification: ..."
gest task complete <task-id> --quiet
```

Committing is VCS hygiene, not a Gest task by itself. Session work does not
auto-commit every small leaf. Development work should commit at verified durable
checkpoints. Session classification alone is not a reason to skip `gcm` for
deployment/runtime config, persistence, public API, user-visible UI, reusable
workflow/template changes, publishable docs, or non-trivial multi-file verified
changes. Before final response for substantial work, inspect
`git status --short --branch`; if Codex-owned changes remain and one of those
triggers applies, run `gcm` or record the concrete no-commit reason.

After Codex pushes a branch other than the repository's mainline branch, the
checkpoint continues through GitHub review: create or update the pull request,
run `gpa`, report the PR review findings/state to the user, and ask whether to
merge. Do not merge without explicit user approval unless the user already asked
for that merge in the current turn.

If a committed branch has no upstream, push with an upstream instead of stopping
locally. After a PR is merged, run any deploy/release command defined by the
target repository's instructions, or report the exact blocker.

## Branch, Stack, And Worktree Policy

For Gest-tracked writes, keep `main` integration-ready and choose both a branch
model and an execution model before editing. Normal session or development work
uses `session/<task-id>-summary` or `gest/<task-id>-summary` branches. Multiple
meaty dependent slices should use stacked branches or stacked PRs. Multiple
independent slices that run at the same time should use separate physical git
worktrees.

GitButler support is sequential by default. GitButler parallel branches and
stacked branches share one managed workspace, so they are branch-curation tools,
not the agent-parallelism primitive. Do not launch parallel write agents in one
GitButler workspace and do not use GitButler parallel lanes for agent
parallelism. If work must run in parallel, use physical worktrees first, then
integrate the results into the intended branch or stack.

In GitButler-managed mode, use current `but` CLI write commands such as
`but branch new`, `but stage`, `but commit`, `but push`, and `but pr`. Do not
use raw `git commit`, `git switch`, `git checkout`, or branch-mutating git
commands while GitButler owns the workspace.

After GitButler PRs are merged and no stack work remains, leave GitButler mode
with `but teardown`, return to the merged base branch, verify it matches its
remote, and clean merged local `session/*` and `gest/*` branches. The terminal
should not be left on `gitbutler/workspace` unless active GitButler work is
continuing.

## Publishing This Repo

After creating a GitHub token/session:

```bash
gh auth login -h github.com
gh repo create agent_gest_git_skills --public --source . --remote origin --push
```

## Tag And Dependency Impact

Before creating Gest tasks, agents should classify work against the existing tag
vocabulary and record selected/rejected/new tags. For code-facing changes, use
`ast-grep` to inspect semantic dependers of changed contracts. See
[`docs/tag_dependency_workflow.md`](docs/tag_dependency_workflow.md).

## Hooks

`install.sh` installs `.claude/` and `.codex/` hooks by default. The GitButler
hooks enforce GitButler mode-strict during active GitButler branch/stack series:
use `but` for writes, reserve raw git writes for explicit physical worktree
execution, and keep tag/dependency checks in view. When a planned flow has
left GitButler mode and is intentionally creating physical worktrees, prefix raw
git worktree commands with `GEST_VCS_EXECUTION=git-worktrees`. Existing repos
can refresh hooks with `scripts/sync_g_skills.sh --hooks /path/to/repo`.
