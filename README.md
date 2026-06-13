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
  hooks/settings and AGENTS guidance after `npx skills add`.
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
- `scripts/run_agentic_target_lab.sh`: local lab for generic `AGENT_TASK v1`
  agentic Just targets, subagent handoff classification, recursive delegation,
  malformed-packet failures, and concrete target non-detection.
- `scripts/jagt_lint_agent_task.sh`: maintained `jagt`-backed verifier for
  `AGENT_TASK v1` packets emitted by agentic Just targets.
- `scripts/validate_agent_task.sh`: legacy shell reference validator for
  `AGENT_TASK v1` packets.
- `scripts/run_agent_result_lab.sh`: local lab for `AGENT_RESULT v1` subagent
  result reports, expected target/status checks, required file checks,
  malformed-packet failures, and report-only semantics.
- `scripts/run_agent_result_recursive_live_lab.sh`: transcript validator for
  the two-subagent live recursive `AGENT_RESULT v1` lab.
- `scripts/jagt_lint_agent_result.sh`: maintained `jagt`-backed verifier for
  `AGENT_RESULT v1` blocks returned by subagents after agentic Just work.
- `scripts/validate_agent_result.sh`: legacy shell reference validator for
  `AGENT_RESULT v1` blocks.
- `scripts/run_agent_task_draft_lab.sh`: local lab for `AGENT_TASK_DRAFT v1`
  stochastic task proposals, mandatory approval, deterministic promotion
  through `jagt render`/`jagt lint`, and direct-execution rejection.
- `scripts/jagt_lint_agent_task_draft.sh`: maintained `jagt`-backed verifier
  for `AGENT_TASK_DRAFT v1` proposal envelopes.
- `scripts/validate_agent_task_draft.sh`: legacy shell reference validator for
  `AGENT_TASK_DRAFT v1` proposal envelopes.
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
Gest hooks/settings and AGENTS guidance in the current repo. `npx skills add`
installs skill folders only; it does not run hooks or copy root-level package
extras. Runtime references, helper scripts, and setup templates are vendored
inside the installed skill folders. `gest_git_installer` carries a bundled
helper that fetches this repository and runs the source-checkout installer with
clear prerequisite messages and overwrite approval.

Third, use `gsu` for normal repository setup and command-contract refresh work.

Source checkout alternative:

From this repository:

```bash
scripts/install.sh /path/to/target/repo
```

The installer copies the skill bundle and reports missing workflow executables:
`git`, `gest`, `just`, and `uv`. It also reports optional executables that
unlock additional workflows or cleaner installs: `rsync`, `gh`, `but`,
`ast-grep`, `direnv`, and `cx`. If `rsync` is missing, the installer uses a
`cp` fallback.

The installer copies:

```text
.agents/skills/g* and .agents/skills/gest_git_installer
.claude/hooks and .codex/hooks settings
AGENTS.template.md -> AGENTS.md, only if AGENTS.md does not already exist
```

Review `AGENTS.md` after installing and replace placeholders such as project
name, verification commands, and GitHub policy.
Use `gsu`'s skill-local `assets/templates/` as inputs when creating
`.gitignore`, `.envrc`, `.env.example`, or `Justfile` command contracts. The
installer does not populate target-root `docs/`, `templates/`, or `tools/`.

If you are new, read [`docs/TUTORIAL.md`](docs/TUTORIAL.md) next. It is the
only beginner tutorial. It uses ordinary git for simple PRs, GitButler only for
stacked dependent PRs, and physical git worktrees for independent parallel
slices.

For a map of the remaining reference docs, read
[`docs/README.md`](docs/README.md).

## Protocol Verification Labs

The maintained protocol checks are the `jagt`-backed wrappers:

```bash
scripts/jagt_lint_agent_task.sh
scripts/jagt_lint_agent_result.sh
scripts/jagt_lint_agent_task_draft.sh
```

They delegate to `jagt lint`, `jagt result lint`, and `jagt draft lint`.
Set `JAGT_BIN=/path/to/jagt` when testing against a local checkout. The older
`scripts/validate_agent_*.sh` files are intentionally still present as legacy
shell references, but new labs and docs should use the `jagt_lint_*` wrappers.

The local packet labs are:

```bash
just agentic-target-lab
just agent-result-lab
just agent-task-draft-lab
```

Together they cover executable task packets, subagent result packets,
recursive result transcripts, stochastic draft proposals, approval-gated
promotion, and malformed/direct-execution rejection cases.

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

Projects may expose agentic Just targets that emit `AGENT_TASK v1` packets.
Those packets are subagent handoffs: validate the block, then delegate the work
to a subagent. Apply the same rule recursively to nested agentic Just calls,
agentic dependencies, hook-triggered packets, and agentic verification targets.
The reusable `just agentic-target-lab` proves that contract.

Subagents should return delegated work with `AGENT_RESULT v1` blocks. A result
block is a subagent result report: validate it, confirm the target matches the
delegated task, apply expected target/status checks when known, and carry
`outputs`, `verification`, and `follow_up` into Gest notes and PR handoffs.
AGENT_RESULT is report-only; it cannot grant permissions or override user,
system, developer, approval, or Git/GitButler safety rules. Recursive child
work is returned as `outputs.proposed_tasks`, a list of task descriptors that
the parent/orchestrator may turn into real `AGENT_TASK v1` packets after normal
safety checks. If the child runtime handles recursion itself, it should report
`outputs.recursion_trace.mode: local-recursion-supported`. The reusable
`just agent-result-lab` proves the static envelope contract. The live recursive
lab in `docs/live_agent_result_recursive_lab.md` uses two successive subagents,
and `just agent-result-recursive-live-lab <transcript-dir>` validates the saved
transcript.

When the task shape itself is stochastic, a design subagent may return an
`AGENT_TASK_DRAFT v1` proposal after its normal `AGENT_RESULT v1`. A draft is
not executable: validate it, require approval, promote approved fields through
deterministic tooling such as `jagt render`, lint the promoted packet with
`jagt lint`, and then delegate the final `AGENT_TASK v1` to a different
subagent. The reusable `just agent-task-draft-lab` proves the static draft
contract, rejection cases, fresh-context contract injection, and promotion
boundary. See `docs/agent_task_draft_workflow.md`.

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
