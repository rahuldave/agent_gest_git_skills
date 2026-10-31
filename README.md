# Agent Gest Git Skills

Reusable agent skills, agent instructions, and small tools for working with
Gest-tracked projects in Git repositories.

This repository is meant to be mixed into other repos. It keeps the workflow
version-controlled without making every project reinvent the same `gtw`, `gim`,
`gpa`, `gcm`, and related skills.

The documentation site is https://rahuldave.github.io/agent_gest_git_skills/. It is built from `docs/`.
`just docs` previews it, and `just docs-publish` publishes it to the branch `gh-pages`.

## What Is Included

- `.agents/skills/g*`: project-local agent skills for setup, Gest workflow routing,
  planning, implementation, review, formatting, testing, docs, promotion,
  pull request acceptance, orchestration, and commits.
- `.agents/skills/gest_git_installer`: package-specific installer skill for
  hooks/settings and AGENTS guidance after `npx skills add`.
- `AGENTS.starter.md`: the starter `AGENTS.md` of a target repo, with the
  project context that you fill in.
- `AGENTS.instructions.md`: the rules of the role. The installer writes them
  to `.agents/instructions/tasker.md` of the target repo.
- `AGENTS.template.md`: the old starter, for an older installer.
- `docs/README.md`: documentation map.
- `docs/TUTORIAL.md`: the deterministic beginner tutorial. Start here.
- `docs/protocol_flows.md`: the agentic packet flow guide and lab map for
  standard `g*` skills plus `AGENT_TASK`, `AGENT_RESULT`, recursive result,
  and task-draft validation.
- `notes/live_protocol_flow_transcript_2026-06-14.md`: real live LLM transcript
  for plain, recursive, unsafe, draft, promotion, and worker result flows.
- `docs/*.md`: reference docs and setup examples for users who need details.
- `docs/integration_delivery_workflow.md`: branch roles, adversarial review,
  CI, delivery, issue completion and installation policy. Gest maintains its
  graphs automatically; no separate graph exporter is shipped.
- `skill-package.json`: package manifest used by `skill-package-maker` to
  validate skills and executable prerequisites. Its `install_extras` names the
  hooks, hook settings and `AGENTS.md` starter that the jnterfaces installer
  copies.
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
- `templates/`: composable setup snippets for `.gitignore`, `.envrc` and
  `.env.example`. The `Justfile` templates are in the `just` skill of
  jnterfaces.

## Install Into A Repo

This repository has no installer of its own. The installer of jnterfaces
installs it in the role `tasker`. A machine needs `just`, `uv` and `git`. In a
project that has the `install` recipe of jnterfaces, run this command:

```bash
just install tasker
```

To start a project without the recipe, clone jnterfaces once and run its
installer. It installs the `just` skill too, which the `g*` skills link to:

```bash
git clone https://github.com/rahuldave/jnterfaces ~/.local/share/skill-packages/jnterfaces
uv run ~/.local/share/skill-packages/jnterfaces/scripts/install_stack.py --profile python tasker
```

The installer clones this repository into the same folder, then copies these
files into the project:

```text
.agents/skills/g* and .agents/skills/gest_git_installer
.claude/hooks and .codex/hooks, and their hook commands in .claude/settings.json and .codex/hooks.json
AGENTS.starter.md -> AGENTS.md, only if AGENTS.md does not already exist
AGENTS.instructions.md -> .agents/instructions/tasker.md, and a line in AGENTS.md that points to it
```

It reports the missing workflow executables, such as `gest`. It checks for
conflicts before it writes, and it keeps existing project instructions and
other settings. The source revision and a hash of each file are in
`.agents/gest-git-install.json`. `just uninstall tasker` takes the package out
again, with its hook commands, and keeps each file that you edited.

With npx, install the skills first, then ask the agent to use
`gest_git_installer`. That skill runs the jnterfaces installer for the hooks,
the hook settings and `AGENTS.md`:

```bash
npx skills add rahuldave/agent_gest_git_skills -a codex --skill '*' -y
npx skills add rahuldave/jnterfaces -a codex --skill just -y
```

Then use `gsu` for normal repository setup and command-contract refresh work.

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

These repository scripts serve the labs here and are not shipped in a skill.
The shipped wrappers are in the `jagt-protocol` skill of jnterfaces.

The local packet labs are:

```bash
just protocol-flow-labs
just agentic-target-lab
just agent-result-lab
just agent-task-draft-lab
```

`protocol-flow-labs` runs the static packet labs in order. Together with
`agent-result-recursive-live-lab <transcript-dir>`, they cover executable task
packets, subagent result packets, recursive result transcripts, stochastic
draft proposals, approval-gated promotion, and malformed/direct-execution
rejection cases. Read [`docs/protocol_flows.md`](docs/protocol_flows.md) for
the full flow map.

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

To update the `g*` skills in a target repository, run `just install` there.
It keeps the skills of other packages and each file that you edited.

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

After Codex pushes a topic or stack branch, the
checkpoint continues through GitHub review: create or update the pull request,
run `gpa`, report the PR review findings/state to the user, and ask whether to
merge. Do not merge without explicit user approval unless the user already asked
for that particular merge; authorization persists across turns.

If a committed branch has no upstream, push with an upstream instead of stopping
locally. After a PR is merged, run any deploy/release command defined by the
target repository's instructions, or report the exact blocker.

See [Integration branches, review, and delivery](docs/integration_delivery_workflow.md)
for the governing policy and references. Mainline and persistent experimental
branches both receive reviewed PRs; experimental integration does not publish
a stable release.

## Branch, Stack, And Worktree Policy

For Gest-tracked writes, keep the selected integration target buildable and choose both a branch
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
integrate the results into the intended branch or stack. Record each worker
worktree's owner, path and branch, plus the separate primary checkout path and
branch; after integration, retire only owned clean worktrees using the checks
in the integration-delivery policy.

In GitButler-managed mode, use current `but` CLI write commands such as
`but branch new`, `but stage`, `but commit`, `but push`, and `but pr`. Do not
use raw `git commit`, `git switch`, `git checkout`, or branch-mutating git
commands while GitButler owns the workspace.

After GitButler PRs are merged and no stack work remains, leave GitButler mode
with `but teardown`, return to the merged base branch, verify it matches its
remote, and clean merged local `session/*` and `gest/*` branches. The terminal
should not be left on `gitbutler/workspace` unless active GitButler work is
continuing.

### Variants and worktree recipes

The tasker role has two variants. Choose one with `just install tasker=gitwt`
or `just install tasker=git`. `just tasker-mode` prints the variant.

| Variant | Where a task works | Parallel tasks |
|---|---|---|
| `git`, the default | A branch in the main checkout | One worktree for each task |
| `gitwt` | A worktree for each task; the main checkout stays on `main` | No more steps |

The package adds these recipes in a project that jnterfaces started. The file
is `.agents/just/roles/agent_gest_git_skills.just`, and the script is
`.agents/skills/gtw/scripts/worktree.py`.

| Recipe | What it does |
|---|---|
| `just worktree-new NAME [BASE]` | Makes branch NAME in `../<repo>.worktrees/NAME`, sets it up, and runs `just setup` there |
| `just worktree-sync` | Sets up a worktree that another tool made, such as Claude Code |
| `just worktrees` | Lists the worktrees: clean or dirty, merged or not, and the ignored files a removal deletes |
| `just worktrees-prune` | Removes clean, merged worktrees that were idle for 2 hours, with no `--force`. Takes `--dry-run`, `--min-age HOURS` and `--with-ignored` |

Setup follows two files in the main checkout, as other tools do:

- `.worktreeinclude` has gitignore patterns. Each file that matches and that
  Git ignores is copied, for example `.env`. Claude Code and Conductor read
  the same file.
- `.worktreelink` has one path on each line. Each path becomes a symbolic link
  to the path in the main checkout, for example a large `data` folder. Git
  sees a link as a file, so the pattern `data/` does not ignore it; write
  `/data` in `.gitignore`. The recipe warns when Git does not ignore a link.

Copy small inputs, link large shared inputs, and keep outputs in each
worktree.

**What prune keeps.** Merged means that a merge of the worktree into the base
would change nothing, so rebased and squashed work counts, and reverted work
does not. A worktree stays when it has ignored files that setup did not put
there, such as outputs or an edited `.env`. `--with-ignored` removes it too.
A detached worktree stays when no branch has its commits.

**Files that a command makes again.** Commands in a worktree make ignored
files. For example, `just setup` makes `.venv`, and the tests make
`__pycache__` and `.pytest_cache`. These files would keep every worktree. So prune reads a
third file in the main checkout, `.worktreedisposable`. It has gitignore
patterns for the ignored files that a command can make again, for example:

```gitignore
.venv/
__pycache__/
.pytest_cache/
```

A removal deletes these files, and they do not keep a worktree. `uv sync
--locked` makes `.venv` again from `uv.lock`. Each profile of jnterfaces
adds its lines to this file, in a block of its own at the start. Your own
lines come after the blocks.

A `!` line names a file that keeps the worktree, for example
`!.venv/keep.txt`. The file keeps it even under a folder that a pattern
excludes.
Patterns match letter case, also on macOS. A package that `uv pip install`
added is not in `uv.lock`, so `uv sync --locked` does not bring it back. Add
such a package with `uv add`, or remove `.venv/` from the file.

## Sibling packages

This package needs the `just` skill of jnterfaces. The other packages are
optional:

- **jnterfaces**, https://github.com/rahuldave/jnterfaces, has the required
  `just` skill and the optional `cx` and `jagt-protocol` skills. They hold the
  Just command contract, the Justfile templates and house style, the jagt
  packet rules and the cx guidance.
- **nossaifd**, https://github.com/rahuldave/nossaifd, has the writing guide
  and its checker.
- **sklanes**, https://github.com/rahuldave/sklanes, has the `lanes` skill,
  which reports requests for human attention to a Lanes inbox.

Each link from a `g*` skill to another package has a fallback in its
paragraph. So the `g*` skills still work when a linked skill is not installed.
The link checker of jnterfaces, `scripts/check_skill_links.py`, checks this
rule. `just lint` runs it, and it needs a jnterfaces clone next to this clone
or in `JNTERFACES_DIR`.

Install the packages with `just install`, the recipe of jnterfaces. It always
installs `just`, and it asks about the other roles. It saves the choices in the
target, so a later run installs them again. See the README of jnterfaces.

`just lint` fails when it finds no jnterfaces clone. Clone jnterfaces next to
this clone, or set `JNTERFACES_DIR`.

A new install removes the skill files that an older install left and that the
source no longer ships, if nobody edited them. For example, it removes the old
copies of `just_command_contract.md`, `cx_incremental_pipelines.md` and the
`jagt_lint_*.sh` scripts. It keeps an edited file and reports it.

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

The installer copies the `.claude/` and `.codex/` hooks. The session-start
hooks name the tasker variant, and they report worktrees that are ready to
prune; they remove nothing. In `gitwt`, a `git commit` in the main checkout gets
a warning, not a block. The GitButler context appears only when `but` is
installed and the checkout is on `gitbutler/workspace`, and never in `gitwt`.

The GitButler hooks enforce GitButler mode-strict during active GitButler branch/stack series:
use `but` for writes, reserve raw git writes for explicit physical worktree
execution, and keep tag/dependency checks in view. When a planned flow has
left GitButler mode and is intentionally creating physical worktrees, prefix raw
git worktree commands with `GEST_VCS_EXECUTION=git-worktrees`. Existing repos
refresh the hooks with `just install`.


## Automatic checks and delivery

GitHub runs `verify-skill-package` on PRs to any branch and on branch pushes.
It checks shell/JSON contracts, hook behavior, canonical reference mirrors,
the package manifest, then exercises GitButler
0.19.9 against both mainline and a distinct persistent integration target.
It builds and verifies a source archive and uploads it as a CI artifact.
`just ci-local` runs the directly available local subset; `just verify` also
runs the broader language/protocol labs with their documented prerequisites.
Automatic CI does not claim that those additional local labs ran.

The authenticated live GitHub lab is manual-only. It requires explicit typed
confirmation and a separately configured `GEST_GITHUB_LAB_TOKEN`; ordinary PR
checks receive no such credential. A merge integrates source. A versioned/tagged
release is a separate request, with package validation, scratch installation,
reviewed source and published artifact verification. No release occurs merely
because an experimental target receives a PR.

## License

MIT. See [LICENSE](LICENSE).
