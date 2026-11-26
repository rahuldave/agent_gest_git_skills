# Agent Gest Git skills

This repository has reusable agent skills, agent instructions and small tools for projects in
Git repositories that track their tasks with Gest. Gest is a command-line task tracker, `gest`.

You mix this repository into other repos. Then the workflow is under version control, and each
project does not have to write its own `gtw`, `gim`, `gpa`, `gcm` and related skills again.

The documentation site is https://rahuldave.github.io/agent_gest_git_skills/. The site comes
from `docs/`. `just docs` shows a preview of it, and `just docs-publish` publishes it to the
branch `gh-pages`.
After a push to `main` passes `verify`, the CI job `docs` runs. It publishes the site of the
newest commit of `main`.

## What is included

- `.agents/skills/g*`: agent skills local to the project. They cover setup, the routing of
  the Gest workflow, plans, implementation, review, format, tests, docs, promotion,
  the acceptance of pull requests, orchestration and commits.
- `.agents/skills/gest_git_installer`: the installer skill of this package. After
  `npx skills add`, it installs the hooks, the hook settings and the AGENTS guidance.
- `AGENTS.starter.md`: the starter `AGENTS.md` of a target repo, with the
  project context that you fill in.
- `AGENTS.instructions.md`: the rules of the role. The installer writes them
  to `.agents/instructions/tasker.md` of the target repo.
- `AGENTS.template.md`: the old starter, for an older installer.
- `docs/README.md`: the documentation map.
- `docs/TUTORIAL.md`: the beginner tutorial, which gives the same result each time. Start
  here.
- `docs/protocol_flows.md`: the guide to the agentic packet flow, and the map of its labs. It
  covers the standard `g*` skills, and the validation of `AGENT_TASK`, `AGENT_RESULT`,
  recursive results and task drafts.
- `notes/live_protocol_flow_transcript_2026-06-14.md`: the transcript of a real live run of an
  LLM. It covers the plain, recursive, unsafe, draft, promotion and worker result flows.
- `docs/*.md`: reference docs and setup examples for users who need details.
- `docs/integration_delivery_workflow.md`: branch roles, adversarial review,
  CI, delivery, issue completion and installation policy. Gest keeps its
  graphs up to date by itself, so the package ships no separate graph exporter.
- `skill-package.json`: the package manifest. `skill-package-maker` uses it to
  validate the skills and the executable prerequisites. Its `install_extras` names the
  hooks, hook settings and `AGENTS.md` starter that the jnterfaces installer
  copies.
- `scripts/run_stack_rebase_lab.sh`: a local lab for a stack of three branches. It runs the
  documented restack commands after one amend, two amends, a new commit and a squash merge. It
  checks that none of them conflicts, and that the old form without `--onto` conflicts.
- `scripts/run_tag_dependency_agent_dry_run.sh`: a local dry run that classifies tags and
  expands the dependencies with `ast-grep`.
- `scripts/run_tag_dependency_typescript_lab.sh`: a live local TypeScript lab. It expands
  the dependencies from Gest tags, and it expands the call sites with `ast-grep`.
- `scripts/run_language_profile_labs.sh`: live local labs that run the setup from start to end.
  Python, TypeScript and Rust use the profiles of jnterfaces, and Go uses the setup snippets.
- `scripts/run_cx_examples_lab.sh`: live local examples of incremental builds with `cx`,
  and of pipelines that make files.
- `scripts/run_agentic_target_lab.sh`: a local lab for generic agentic targets of the
  Justfile that print `AGENT_TASK v1`. It checks the classification of a subagent handoff,
  recursive delegation and the failures of malformed packets. It also checks that a concrete
  target is not detected as agentic.
- `scripts/jagt_lint_agent_task.sh`: the maintained verifier, on top of `jagt`, for the
  `AGENT_TASK v1` packets that agentic targets of the Justfile print.
- `scripts/validate_agent_task.sh`: a validator in shell for `AGENT_TASK v1` packets,
  kept as a legacy shell reference.
- `scripts/run_agent_result_lab.sh`: a local lab for the `AGENT_RESULT v1` reports that
  subagents return. It runs the expected target/status checks and the required file checks.
  It also checks that malformed packets fail, and that a subagent result only reports.
- `scripts/run_agent_result_recursive_live_lab.sh`: the validator of the transcript of
  the live recursive `AGENT_RESULT v1` lab, which uses two subagents.
- `scripts/jagt_lint_agent_result.sh`: the maintained verifier, on top of `jagt`, for the
  `AGENT_RESULT v1` blocks that subagents return after agentic work from the Justfile.
- `scripts/validate_agent_result.sh`: a validator in shell for `AGENT_RESULT v1` blocks,
  kept as a legacy shell reference.
- `scripts/run_agent_task_draft_lab.sh`: a local lab for the stochastic task proposals of
  `AGENT_TASK_DRAFT v1`. It checks that a draft needs approval, and that `jagt render` and
  `jagt lint` promote it the same way each time. It also checks that the tools reject a
  direct run of a draft.
- `scripts/jagt_lint_agent_task_draft.sh`: the maintained verifier, on top of `jagt`, for
  `AGENT_TASK_DRAFT v1` proposal envelopes.
- `scripts/validate_agent_task_draft.sh`: a validator in shell for `AGENT_TASK_DRAFT v1`
  proposal envelopes, kept as a legacy shell reference.
- `templates/`: setup snippets that you can combine, for `.gitignore`, `.envrc` and
  `.env.example`. The `Justfile` templates are in the `just` skill of
  jnterfaces.

## Install into a repo

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
.agents/skills/gsu/assets/templates/github-check.yml -> .github/workflows/check.yml, only if that file does not already exist
.agents/skills/gsu/assets/templates/github-release.yml -> .github/workflows/release.yml, only if that file does not already exist
```

The CI job in `.github/workflows/check.yml` checks out the whole history and
runs `just ci` on each pull request. The step `release-check` of `just check`
fails when the language profiles give different versions, or a version lower
than the last tag. A pull request does not raise the version.

The CI job in `.github/workflows/release.yml` runs `just check` on each push
to `main`. When the check passes, it runs `just release`. The release writes
the bump into the version files, commits it as `github-actions[bot]`, and
tags the release. Both files are yours from then on. Add the setup of the
tools of your languages to them when the runner lacks them.

**Rust in CI.** Both starters have Rust steps. They run only when the project
has a toolchain file, `rust-toolchain.toml` or `rust-toolchain`. Other
projects skip them.

- `just install` of jnterfaces writes `rust-toolchain.toml` with the exact
  version of the Rust of your machine. No template of this package gives the
  file, because a version in a template goes stale. Commit the file.
- A project with a `Cargo.toml` and no toolchain file fails at the first Rust
  step. The message says to run `just install` and commit the file.
- `rustup toolchain install` reads the toolchain file. No step names a
  channel such as `stable`, so CI runs the same compiler and clippy as your
  machine.
- A channel that moves, such as `stable` or `1.95`, gets a warning. Pin an
  exact version, such as `1.95.0`.
- The step stops when `RUSTUP_TOOLCHAIN` is set, and when `rustc -V` prints
  no version.
- `cargo-llvm-cov` 0.9.1 comes as a release binary, so no run compiles it.
- With `JNPROFILE_RUST_NEXTEST=1`, jnprofile-rust runs its integration tests
  with `cargo llvm-cov nextest`. Then the starters also install
  `cargo-nextest` 0.9.151 as a release binary. Set `JNPROFILE_RUST_NEXTEST:
  "1"` in the `env` at the top of both `check.yml` and `release.yml`, or in
  the job `ci` of `check.yml` and the job `check` of `release.yml`. The
  value must be exactly `1`. An `env` of only one step, or a repository
  variable, does not turn on the install.

**The pins of the starters.** Each job installs its tools in one step, "Install
the pinned tools". The step downloads `just` 1.59.0 and `uv` 0.13.7. It
also downloads the jlog that the CI of jnterfaces pins, and in a Rust job
`cargo-llvm-cov` and `cargo-nextest`.

Each download must have the SHA-256 that the step itself pins, for Linux on x86_64
and on aarch64. The server of a download keeps its own `.sha256` file, but a
person who can change the download can change that file too. So a changed
download stops the job.

The install script of jlog comes from the full SHA of the commit of its tag,
and the step checks it against a pin too. No action installs a tool. Each
action, such as `actions/checkout`, is pinned by the full SHA of its commit,
with its version in a note after it. A tag can move to another commit, but a
SHA cannot.

To bump a pin:

1. Pick a version that is at least two weeks old.
2. For an action, find the commit of the tag with
   `git ls-remote https://github.com/actions/checkout 'refs/tags/v4.4.0' 'refs/tags/v4.4.0^{}'`.
   If the output has a line that ends in `^{}`, the tag is annotated, so take
   the SHA of that line, which is the commit. Write the SHA, then the note
   `# v4.4.0`.
3. For a tool, change the version in its `fetch` line and in its two pins.
   Then download both archives and run `sha256sum` on each, or read the
   digest of each with `gh release view TAG -R OWNER/REPO --json assets`.
4. Write each SHA-256 in the list `pins` of the step, in each job of both
   files.
5. Run `JN_TEST_NETWORK=1 just lint` in a clone of this package after you
   change a starter here. The test downloads each pin and checks its SHA-256,
   and it checks that the SHA of each action is the commit of its tag.
   `just lint` without the variable checks that each action has a full SHA
   and that `just` and `uv` have exact versions.

**Path dependencies in the cache.** A path dependency is a package in the
repository that is not a member of the workspace, such as a crate with C code
in `vendor/`. cargo makes each path dependency under the root of a workspace
a member, unless `workspace.exclude` names it. A package with no
`[workspace]` has no such members.

A fresh checkout gives each of its files the time of now. cargo
takes a build as up to date only when the build is newer than its sources, so
it builds each path dependency again on each run, also with a warm cache. Set
`JN_CI_PATH_DEP_TIMES: "1"` in the `env` of both workflows, or of the job `ci`
of `check.yml` and the job `check` of `release.yml`, to turn on the step "Set
the times of the path dependencies":

- `cargo metadata --no-deps --offline` names the members of the workspace and
  their path dependencies, with no network. The step also reads the `[patch]`
  and `[replace]` of `Cargo.toml`, and the path dependencies of each path
  dependency.
- Each file that Git tracks in a path dependency gets a fixed time in the
  year 2000, and so does each folder that holds such a file. A member keeps
  the time of the checkout, so cargo builds it again.
- The step hashes the path, the mode and the bytes on the disk of each of
  those files, the target of each link, and the commit of each submodule.
  Each level of the key of the cache holds this hash.
- When the variable is 1 and the step finds no path dependency, it gives a
  warning.

An old time is a danger. If a cache holds a build of other files, cargo takes
that build as up to date, and the check passes on code that it did not build.
The hash in each level of the key stops this, because a run restores only a
cache that a run with the same files built. A level without the hash could
restore a build of an older version of the vendored code. The job `check` of
`release.yml` also saves no cache when the check changed a file of a path
dependency. A path dependency that the step does not find keeps the time of
the checkout, so cargo builds it again, and the result is correct.

Do not turn on the step when a build script of a path dependency reads a file
outside its folder and names no `rerun-if-changed` for it. Without the step,
such a build ran again on each run. With the step, cargo can keep an old
build of it.

The step is off by default, because it has a cost. Each change of a file of a path
dependency starts a new cache from nothing, with a cold build of each crate.
A project whose vendored code changes often can lose more time than it saves.
And a fault in the step would give a false pass, not a slow run. So turn it
on only when CI builds a path dependency for a long time on each run, and
compare the time of the job before and after.

**The Rust cache.** A cache keeps `~/.cargo/registry/index`,
`~/.cargo/registry/cache`, `~/.cargo/git/db` and `target/`. `target/` holds
`target/llvm-cov-target`, the warm build of the coverage step. The cache keeps all
of `target/`, because cargo also writes files under
`target/debug/build/<pkg>/<hash>/out/`. The key has
six parts:

1. the runner, such as `Linux-X64`;
2. the compiler, as `rustc -V` prints it, such as `1.95.0-59807616e-2026-04-14`.
   A channel that moves gets a new key with each new compiler;
3. the word `check`, which each job that runs `just check` uses, so a pull
   request restores the cache of `main`;
4. the word `paths`, then the hash of the path dependencies, or `none` when
   the step for path dependencies is off or finds none;
5. the hash of each `Cargo.lock`;
6. the commit, `github.sha`.

A restore first takes the newest cache with the same `Cargo.lock`, then the
newest cache of the same compiler. Each level also holds the hash of the path
dependencies. A pull request only restores. Each push to
`main` that passes `just check` saves a new cache, so the cache of `main`
stays up to date. Each save uploads the whole cache, which can take some
gigabytes, so the job `check` on `main` takes longer by the time of that
upload. The job `release` waits for it.

GitHub keeps 10 GB of caches for each repository. When the caches pass that
size, GitHub removes the caches that no run used for the longest time. It
also removes a cache that no run used for 7 days. The restore takes only the
newest cache, so an old cache that GitHub removes costs nothing. The 10 GB
also hold the other caches of the repository, such as the cache of uv. Look at
the caches under Actions, Caches, when the Rust cache is big.

A `CARGO*` or `RUST*` variable that changes on each run, such as one from
`github.run_id`, makes the coverage build clean itself on each run. Do not set
one. The commit in the key is no variable, so it does not change the build.

It reports each workflow executable that is missing, such as `gest`. It checks for
conflicts before it writes, and it keeps the instructions and the other settings that the
project already has. The source revision and a hash of each file are in
`.agents/gest-git-install.json`. `just uninstall tasker` takes the package out
again, with its hook commands, and keeps each file that you edited.

With npx, install the skills first, then ask the agent to use
`gest_git_installer`. That skill runs the jnterfaces installer for the hooks,
the hook settings and `AGENTS.md`:

```bash
npx skills add rahuldave/agent_gest_git_skills -a codex --skill '*' -y
npx skills add rahuldave/jnterfaces -a codex --skill just -y
```

Then use `gsu` to set up the repository and to refresh its command contracts.

After the install, review `AGENTS.md`, and replace the placeholders, for example the name of
the project, the verification commands and the GitHub policy.
When you create `.gitignore`, `.envrc`, `.env.example` or the command contracts of a
`Justfile`, use the `assets/templates/` folder of the `gsu` skill as inputs. The installer
does not fill `docs/`, `templates/` or `tools/` at the root of the target.

If you are new, read [`docs/TUTORIAL.md`](docs/TUTORIAL.md) next. It is the
only beginner tutorial. It uses ordinary git for simple PRs, stacked PRs with
plain git for dependent slices, and physical git worktrees for independent
parallel slices.

For a map of the other reference docs, read
[`docs/README.md`](docs/README.md).

## Protocol verification labs

The maintained protocol checks are wrappers on top of `jagt`:

```bash
scripts/jagt_lint_agent_task.sh
scripts/jagt_lint_agent_result.sh
scripts/jagt_lint_agent_task_draft.sh
```

They delegate to `jagt lint`, `jagt result lint` and `jagt draft lint`.
To test with a local checkout of `jagt`, set `JAGT_BIN=/path/to/jagt`. The older
`scripts/validate_agent_*.sh` files stay on purpose as legacy shell references. But new labs
and docs should use the `jagt_lint_*` wrappers.

The labs of this repository use these scripts, and no skill ships them.
The shipped wrappers are in the `jagt-protocol` skill of jnterfaces.

The local packet labs are:

```bash
just protocol-flow-labs
just agentic-target-lab
just agent-result-lab
just agent-task-draft-lab
```

`protocol-flow-labs` runs the static packet labs in order. Together with
`agent-result-recursive-live-lab <transcript-dir>`, the labs cover these cases:

- executable task packets and subagent result packets
- transcripts of recursive results
- stochastic draft proposals, and their promotion after approval
- the rejection of malformed packets and of a direct run of a draft

Read [`docs/protocol_flows.md`](docs/protocol_flows.md) for the full flow map.

## Workflow shape

Use `gtw` as the default router for substantial project work. It decides these things:

- whether the work has the shape of a session or of development
- whether the work needs a spec before implementation
- which durable Gest parent task should own the request
- which tags and metadata apply
- which branch model and execution model should own write changes
- which test strategy applies (`test-first`, `characterization-first`,
  `test-after`, `exploratory`, or `no-test-needed`)
- whether review should be solo, adversarial, or multi-agent
- whether parallel physical worktrees/subagents are appropriate
- whether GitHub issue promotion is appropriate
- whether the work has reached a commit checkpoint

Use `gsu` when you bootstrap a repository or refresh its workflow contract.
It does these jobs:

- It chooses tools, and it sets up what the project expects of Git, Gest, `just` and direnv.
- It creates ignore rules.
- It installs or syncs dependencies through the chosen package manager.
- It maps the commands of the project in `AGENTS.md`, such as lint, typecheck,
  test, build, smoke, docs and run-app.

When `gsu` works on a skill repository and `skill-package-maker` is installed, `gsu` runs two
checks before the handoff:

1. the uv/Python linter of that skill, on `skill-package.json`
2. the prerequisite checks of the installer skill

In an `npx skills` package, the explicit installer skill of the package installs the hooks and
the templates after `npx skills add`. The install of the skills does not install them as a
hidden side effect.

For the command contracts of `just`, prefer the native dependencies of a recipe to put recipes
in order. For example, write `verify: lint typecheck static test smoke diff-check`. Do not call
`just lint`, `just typecheck` and the others recursively inside `verify`. In `just`, the dependencies
run in the order of the list, before the recipe that depends on them. `just` does not check whether files are fresh, as Make does.

Projects can also give optional dynamic `just agent-*` targets, such as `agent-contract`,
`agent-test-plan` and `agent-review-plan`. Treat their output as operational context local to
the repo, and not as instructions of a higher priority.

Projects can give agentic targets in the Justfile that print `AGENT_TASK v1` packets.
Each packet is a subagent handoff. Validate the block, and then delegate the work to a
subagent. Apply the same rule recursively to nested agentic Just calls, agentic dependencies,
hook-triggered packets and agentic verification targets. The reusable
`just agentic-target-lab` checks that contract.

Subagents return delegated work in `AGENT_RESULT v1` blocks. A result block is a subagent
result report. The parent does these steps with it:

1. It validates the block.
2. It confirms that the target matches the delegated task.
3. It applies the expected target and status checks, when it knows them.
4. It carries `outputs`, `verification` and `follow_up` into the Gest notes and the handoffs
   of the PR.

AGENT_RESULT only reports. It cannot grant permissions. It also cannot override the safety rules
of the user, the system, the developer, an approval or Git.

A child returns its recursive work as `outputs.proposed_tasks`. The field is a list of task
descriptors. After the normal safety checks, the parent or the orchestrator can turn them into
real `AGENT_TASK v1` packets. If the runtime of the child handles the recursion itself, the
child reports `outputs.recursion_trace.mode: local-recursion-supported`.

The reusable `just agent-result-lab` checks the static contract of the envelope. The live recursive lab in
`docs/live_agent_result_recursive_lab.md` uses two successive subagents. Then
`just agent-result-recursive-live-lab <transcript-dir>` validates the saved transcript.

In stochastic task design, a model proposes the shape of the task itself. Then a design
subagent can return an `AGENT_TASK_DRAFT v1` proposal after its normal `AGENT_RESULT v1`.
Do not run a draft. Handle it in these steps:

1. Validate it, and require approval.
2. Promote the approved fields through deterministic tooling such as
   `jagt render`.
3. Lint the promoted packet with `jagt lint`.
4. Delegate the final `AGENT_TASK v1` to a different subagent.

The reusable `just agent-task-draft-lab` checks these parts of the draft:

- the static contract of the draft and its rejection cases
- the injection of the contract into a fresh context
- the boundary of the promotion

For the details, read `docs/agent_task_draft_workflow.md`.

`just cx-examples-lab` runs two `cx` examples. One is a staged artifact
pipeline, and one is an explicit incremental C build. Use `cx` only for the build or pipeline
stages that make files, inside linewise recipes of the Justfile. Do not use it for tests or
for the ordinary builds of a package manager.

To update the `g*` skills in a target repository, run `just install` there.
It keeps the skills of other packages and each file that you edited.

The description of a Gest task records its intent. Before a leaf task that is not trivial
is complete, give it a task note:

```bash
gest task note add <task-id> --agent codex --body "Done: ...\nVerification: ..."
gest task complete <task-id> --quiet
```

A commit is part of the hygiene of the VCS, and it is not a Gest task by itself. Session work
does not commit each small leaf automatically. Development work commits at verified durable
checkpoints. A session classification alone is not a reason to skip `gcm` for these changes:

- deployment or runtime config, or persistence
- a public API or a UI that users see
- changes to a reusable workflow or template, or docs that are published
- verified changes to several files that are not trivial

Before the final response for substantial work, inspect `git status --short --branch`. If
changes that Codex owns remain and one of these triggers applies, run `gcm`. Or record the
concrete reason not to commit.

After Codex pushes a topic branch or a stack branch, the checkpoint continues through the
review on GitHub:

1. Create or update the pull request.
2. Run `gpa`.
3. Report the PR review findings and state to the user.
4. Ask whether to merge.

Do not merge without the explicit approval of the user. The exception is a merge that the user
already asked for. The approval of that merge lasts across turns.

If a committed branch has no upstream, push it with an upstream, and do not stop with the
branch only local. After a PR is merged, run each deploy or release command that the
instructions of the target repository define. Or report the exact blocker.

[Integration branches, review, and delivery](docs/integration_delivery_workflow.md) gives the
policy and its references. The mainline and the persistent experimental branches both receive
reviewed PRs. An experimental integration does not publish a stable release.

## Branch, stack, and worktree policy

For writes that Gest tracks, keep the selected integration target buildable. Before you edit,
choose both a branch model and an execution model:

- Normal session or development work uses `session/<task-id>-summary` or
  `gest/<task-id>-summary` branches.
- Several large slices that depend on each other use stacked branches or stacked PRs.
- Several independent slices that run at the same time use separate physical git worktrees.

Two agents must not write in one folder at the same time. A branch in the main checkout is
for work in order, one task after the other.

If work must run in parallel, use physical worktrees first. Then integrate the results into
the intended branch or stack. Record the owner, the path and the branch of each worker
worktree, and the path and the branch of the separate primary checkout. After the integration,
retire only the clean worktrees that you own, with the checks of the integration-delivery
policy.

A stack of dependent PRs uses plain git and `gh`:

1. Start each branch from the branch below it, for example with
   `git switch -c <child-branch> <parent-branch>`.
2. Open the PR of each branch with `gh pr create --base <parent-branch>`, from the bottom
   branch up.
3. After a change to a lower branch, switch to the top branch and run
   `git rebase --update-refs --onto <lower-branch> <old-lower-tip>`. `<old-lower-tip>` is the
   commit of the lower branch before the change. Save it with `git rev-parse <lower-branch>`
   before you change the branch. `<lower-branch>@{1}` is that commit only after one change.
   The rebase replays only the commits above the lower branch, and it moves each branch of the
   stack between them. It does not move a branch that another worktree has checked out. The
   option needs git 2.38 or later.
4. Push each moved branch with `git push --force-with-lease`.

After the PRs are merged and no stack work remains, do these steps:

1. Return to the merged base branch, and verify that it matches its remote.
2. Clean merged local `session/*` and `gest/*` branches.

### Variants and worktree recipes

The tasker role has two variants. Choose one with `just install tasker=gitwt`
or `just install tasker=git`. `just tasker-mode` prints the variant.

| Variant | Where a task works | Parallel tasks |
|---|---|---|
| `git`, the default | A branch in the main checkout | One worktree for each task |
| `gitwt` | A worktree for each task; the main checkout stays on `main` | No more steps |

The package adds these recipes in a project that jnterfaces started. The file
is `.agents/just/roles/agent_gest_git_skills.just`. The scripts are
`.agents/skills/gtw/scripts/worktree.py`,
`.agents/skills/gcm/scripts/stack_prs.py` and
`.agents/skills/gpa/scripts/release_tag.py`.

| Recipe | What it does |
|---|---|
| `just worktree-new NAME [BASE]` | Makes branch NAME in `../<repo>.worktrees/NAME`, sets it up, and runs `just setup` there |
| `just worktree-sync` | Sets up a worktree that another tool made, such as Claude Code |
| `just worktrees` | Lists the worktrees: clean or dirty, merged or not, and the ignored files a removal deletes |
| `just worktrees-prune` | Removes clean, merged worktrees that were idle for 2 hours, with no `--force`. Takes `--dry-run`, `--min-age HOURS` and `--with-ignored` |
| `just stack-prs BASE BRANCH...` | Opens the PRs of a stack in order, from the bottom branch up, each on the branch below it. Pushes a branch with no upstream or ahead of it, never with force. Takes `--dry-run` first |
| `just release` | Tags the next release `vX.Y.Z` by semver, pushes the tag and checks it on the remote. The number comes from the commits since the last tag. When the version files of the language profiles are lower, it writes the bump into them, commits it as `chore(release): vX.Y.Z` and tags that commit. A run on a released commit, or on the parent of its version commit, prints `already released` and gives the tag again. Never moves or deletes a tag. Takes `--dry-run` first |

Setup follows three files in the main checkout:

- `.worktreeinclude` has gitignore patterns. Each file that matches and that
  Git ignores is copied, for example `.env`. Claude Code and Conductor read
  the same file.
- `.worktreelink` has one path on each line. Each path becomes a symbolic link
  to the path in the main checkout, for example a large `data` folder. Git
  sees a link as a file, so the pattern `data/` does not ignore it. Write
  `/data` in `.gitignore`. The recipe warns when Git does not ignore a link.

- `.worktreeseed` has one build folder on each line. When a new worktree has
  no such folder and the main checkout has one, `just worktree-new` copies it
  with copy-on-write. So the first build uses the compiled dependencies again.
  With no `.worktreeseed`, a project with a `Cargo.toml` seeds `target`. An
  empty file seeds nothing.

Copy small inputs, link large shared inputs, and keep outputs in each
worktree.

**The seed of a build folder.** `just worktree-new` seeds a folder only when
Git ignores it. It copies with `cp -c -p -R` on macOS and `cp --reflink=auto -p -R` on
Linux:

- On APFS, Btrfs and XFS, the copy takes seconds. It uses no more disk space
  until a file changes.
- On ext4, `--reflink=auto` makes a full copy. It is correct, but it takes
  the time and the disk space of the whole folder, which can be some
  gigabytes. Delete `target` in the worktree, or write an empty
  `.worktreeseed`, if you do not want this.
- A failed copy leaves no folder, and the first build makes it. The copy goes
  into a folder in the Git folder of the worktree, and a rename puts it in
  place.
- The copy keeps the time of each file, on macOS and on Linux. A test of the
  package checks this with the `cp` of each system.
- The copy leaves out `target/llvm-cov-target/jnprofile-rust-build.txt`. This
  stamp of jnprofile-rust records a coverage build of the commit of the main
  checkout. A worktree of another commit must not trust that build, so the
  first coverage run in the worktree builds again.
- cargo takes a build as up to date when it is newer than its sources. So
  after the seed, each file that Git tracks in the worktree gets the time of
  now. Then cargo builds the crates of the project again and reuses only the
  builds of the dependencies. A test builds a worktree of another commit with
  cargo, while a build in the main checkout runs during the seed, and checks
  that the program of the worktree prints the text of its own commit.
- `just worktree-sync` does not seed. Only a new worktree gets a seed.

The seed is always a copy. It is never a link, and the worktrees never share
one `CARGO_TARGET_DIR`. Two worktrees that share a build folder see each
other's builds, so clippy can pass on code that it did not check. A seeded
folder does not keep a worktree at prune, since a build makes it again.
`--no-setup` skips only `just setup`, so the seed still takes place.

**What prune keeps.** Merged means that a merge of the worktree into the base
would change nothing. So rebased and squashed work counts as merged, and reverted work
does not. A worktree stays when it has ignored files that setup did not put
there, such as outputs or an edited `.env`. `--with-ignored` removes it too.
A detached worktree stays when no branch has its commits.

**Files that a command makes again.** Commands in a worktree make ignored
files. For example, `just setup` makes `.venv`, and the tests make
`__pycache__` and `.pytest_cache`. These files would keep every worktree. So prune reads a
fourth file in the main checkout, `.worktreedisposable`. It has gitignore
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
rule. `just lint` runs it, and it needs a jnterfaces clone. See below for how
the checks find the clone.

Install the packages with `just install`, the recipe of jnterfaces. It always
installs `just`, and it asks about the other roles. It saves the choices in the
target, so a later run installs them again. See the README of jnterfaces.

The checks and labs find the jnterfaces clone with
`scripts/find_jnterfaces.sh`. They use the first of these folders:

1. `JNTERFACES_DIR`, when you set it. Then they use no other folder.
2. The folder `jnterfaces` next to this clone.
3. The installed copy, `~/.local/share/skill-packages/jnterfaces`. Set
   `SKILL_PACKAGES_DIR` to use another folder than `~/.local/share/skill-packages`.
4. A clone of the commit that CI tests, in
   `~/.cache/agent_gest_git_skills`. The first check without another clone
   makes this clone from GitHub, so it needs the network once.

So `just check` also works in a clone outside the folder of your projects. Each
check uses the first clone that it finds, and fails when that clone does not have
the file that it needs.

A new install removes the skill files that an older install left and that the
source no longer ships, if nobody edited them. For example, it removes the old
copies of `just_command_contract.md`, `cx_incremental_pipelines.md` and the
`jagt_lint_*.sh` scripts. It keeps an edited file and reports it.

## Publish this repo

After you create a GitHub token or session, run these commands:

```bash
gh auth login -h github.com
gh repo create agent_gest_git_skills --public --source . --remote origin --push
```

## Tag and dependency impact

Before agents create Gest tasks, they classify the work against the tag vocabulary that
exists. They record the selected, the rejected and the new tags. For a change to code, use
`ast-grep` to inspect the code that depends on a changed contract. For the details, read
[`docs/tag_dependency_workflow.md`](docs/tag_dependency_workflow.md).

## Hooks

The installer copies the `.claude/` and `.codex/` hooks. The session-start
hooks name the tasker variant, and they report the worktrees that are ready to
prune. They remove nothing. In `gitwt`, a `git commit` in the main checkout gets
a warning, not a block.

The `SubagentStop` hook `record-result.sh` runs when a subagent stops. It
writes the record of the result of a fresh agent, which the commit gate needs.
When a fresh agent of a packet stops with no result block, the hook writes
the facts in `.agents/log/hook-stops/<agent_id>.json`. A stop with no
transcript path also writes that file. Another subagent with no block gets no
wait and no file. The hook never stops the agent.

The section "Records" of
[`docs/specs/commit-gates.md`](docs/specs/commit-gates.md) tells how.

The installer also installs the pre-commit framework and its git hooks, from
`.pre-commit-config.yaml`:

- **pre-commit and pre-merge-commit** run the commit gate. The gate stops a
  commit without a pass of `just check` for its tree, and an agent commit
  without the records of its required targets.
- **commit-msg** runs the gate again. Then it runs `just release-check` on the
  message of the commit, since v0.3.5. A commit whose type asks for a
  release, such as `fix:`, stops when the release cannot write the version
  file of a profile. The hook skips this check for a merge, for an amend of
  a merge, during a rebase, and when the Justfile has no recipe
  `release-check`. When both checks pass, the hook adds the trailer
  `Commit-Gate:` to the message. CI checks the trailer of each commit.
- **pre-push** runs `just ci`, so a push checks on your machine what CI
  checks. It skips each recipe that a pass of `just check` for the pushed
  tree ran, and it always checks the trailers.

### The check of the trailers

The step `ci-gate` checks that each commit of a pull request passed the
commit gate. It reads only git, so CI can run it with no agent.
It is a step of `just check` and of `just ci`, so CI runs only steps of
`just check`.

- **The commits.** `ci-gate` checks the commits from the merge-base with the
  base branch to HEAD. In CI, the base is `JN_CI_BASE`, the base of the pull
  request. On your machine, the base is `origin/HEAD`, `origin/main` or
  `origin/master`. A clone with no base passes with a note, but in CI a
  missing base fails.
- **A valid trailer.** The commit has one `Commit-Gate:` trailer with one
  word, `patch:<id>`. The ID is the patch ID of the commit, which `ci-gate`
  computes again from the commit. So a commit that changed after the gate
  passed it fails.
- **The exempt commits.** `ci-gate` skips each of these commits and names
  it:
  - A merge with no change of its own. Its tree is the tree that
    `git merge-tree` makes from its two parents, as for the merge of a pull
    request on GitHub. Another merge needs the trailer `tree:<tree>` of the
    gate.
  - A commit whose author is a GitHub bot, such as
    `49699333+dependabot[bot]@users.noreply.github.com`. The version commit
    of the release job, `chore(release): vX.Y.Z`, is such a commit.
  - A commit from before the gate. No commit that it reaches changed
    `.agents/stack.json`, so the gate could not run. This repository has no
    `.agents/stack.json`, so its own commits are of this kind.
  - A commit that you make on the GitHub website, such as with its
    "Revert" button, is not exempt. Make it on your machine instead.
- **The fix.** The error names each bad commit by its hash and subject. To
  fix the newest commit, run `git reset --soft HEAD~1`, then `just check`,
  then `git commit -C ORIG_HEAD`. For an older commit, run `git rebase -i`
  on its parent, and mark the commit `edit`. Do the same at the stop, then
  run `git rebase --continue`. When the bad commits are not yours, the base
  is wrong. Give it, as `JN_CI_BASE=origin/develop just check`.
- **A shallow clone.** The check stops in a shallow clone, since it needs
  the parents of each commit. Use `fetch-depth: 0` in CI.
- **The limit.** A trailer is a claim, not a proof. A person can type a
  trailer or a bot e-mail by hand. The review of the pull request checks
  that.

The hooks need a jnterfaces installer that runs the `programs` of a role. An
older one installs no hook and gives no error. The specification is
[`docs/specs/commit-gates.md`](docs/specs/commit-gates.md).
Before a commit, a push or `gh pr create`, the Claude Code hook gives the agent
the commit rules of `docs/dev/commits.md`, if the project has that file. A repo
that already has the hooks refreshes them with `just install`.

## Automatic checks and delivery

GitHub runs `verify-skill-package` on PRs to any branch and on each push to a branch.
It checks the shell and JSON contracts, the behavior of the hooks, the mirrors of the
canonical references and the package manifest. It builds and verifies a source archive, and it
uploads the archive as a CI artifact.

CI runs `just check` and no other check, so `just check` finds each failure of CI. It runs
`just release-check`, `just ci-gate`, `just lint`, `just package-lint`, `just stack-rebase-lab`,
`just install-test`, `just source-archive` and `just diff-check`. `just package-lint` clones
skill-package-maker from GitHub, so `just check` needs the network. `just lint` and `just install-test` need a
clone of jnterfaces, which `scripts/find_jnterfaces.sh` finds. CI tests the commit of
jnterfaces in `scripts/jnterfaces_commit`, and `just lint` and `just install-test` warn when the clone
is at another commit or has changes that are not committed.

`just verify` also runs the broader labs for languages and protocols, with the prerequisites that their docs
give. The automatic CI does not claim that these extra local labs ran.

A merge integrates the source. A release with a version or a tag is a separate request. It
needs the validation of the package, an install into a scratch folder, reviewed source and the
verification of the published artifact. A PR to an experimental target does not make a release
by itself.

## License

MIT. See [LICENSE](LICENSE).
