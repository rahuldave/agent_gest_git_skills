# Agent Instructions

This repository uses Gest to track substantial implementation work. Use the
project-local Codex skill family under `.agents/skills/`, especially `gtw`, for
coding, debugging, implementation, refactoring, documentation, verification, and
project planning.

The user may invoke the router as `$gtw`, `gtw:`, or `/gtw`.
Use `gsu` for repository bootstrap, setup refresh, tool selection, ignore
rules, installs, command-contract mapping, and Justfile creation.

If a request is substantial enough for Gest tracking but no `g*` command was
explicitly invoked, still use the appropriate Gest workflow. If an agent chooses
not to use Gest for a coding/debugging/refactoring/documentation/verification
request, it must say why in the final response.

## Project Context

- Project name: `<replace-me>`
- Main source directory: `<replace-me>`
- Primary docs/specs: `<replace-me>`
- Detailed workflow playbook: `docs/gest_codex_workflow.md`

Replace this section with project-specific invariants, runtime commands, and
verification commands.


## Tag And Dependency Impact

Before creating or splitting Gest tasks, collect the existing project tag
vocabulary and classify the work against it. Record selected existing tags, new
dynamic tags, and near-miss rejected tags when useful. Store machine-readable
metadata such as `classification.tags.reviewed=true`,
`classification.tags.new=<comma-separated-new-tags>`, and
`impact.ast_grep.required=true|false`. Use `docs/tag_dependency_workflow.md` for
the exact workflow.

For code-facing changes, identify changed semantic contracts and use `ast-grep`
to inspect dependers. If a task changes one surface of a coupled concept, expand
the task or create/link a child task for the other surface before completion.
Completion notes should include `Tag classification:` and `Dependency impact:`
for code-facing work.

## Gest Workflow

Before creating new tasks, search and inspect existing work:

```bash
gest search "<project keyword>" --all --json
gest task list --all --json
gest iteration list --all --json
```

Serialize Gest commands. Current forked Gest builds from June 8, 2026 and later
prefer `.gest/gest.db` for local projects without explicit `database.url` or
`storage.data_dir` overrides, which normally keeps SQLite inside the writable
workspace. Legacy or stock system Gest builds may still use the global database
at `~/Library/Application Support/gest/gest.db`; in sandboxed environments,
keep the old workaround for those installs by running mutations with local
approval and retrying readonly sync-import warnings with the same narrow
`gest` approval.

Use native Gest `child-of` / `parent-of` links for hierarchy. Tags are filters,
not hierarchy. Claim one leaf task at a time, verify before completion, and keep
long-lived outline parents open until the whole subtree is done.

For any Gest-tracked work that writes files, choose a VCS branch model and
execution model before editing. Branch names should be keyed to the highest
meaningful Gest task for the workstream, for example
`gest/<task-id-short>-two-word-summary` or
`session/<task-id-short>-two-word-summary`.

Use a normal session/development branch for one coherent workstream. Use stacked
branches for multiple meaty dependent slices that should be separately
reviewable. Use physical git worktrees for multiple independent write tasks
running at the same time.

GitButler parallel branches and stacked branches share one managed workspace.
They are sequential branch-curation tools for agents, not an agent-parallelism
primitive. Do not launch parallel write agents in one GitButler workspace or use
GitButler parallel lanes for agent parallelism. If parallel work is needed, use
separate physical worktrees first and integrate the results into the intended
branch or stack afterward.

When GitButler owns the workspace, use current `but` CLI write commands such as
`but branch new`, `but stage`, `but commit`, `but push`, and `but pr`. Do not
use raw `git commit`, `git switch`, `git checkout`, or branch-mutating git
commands in GitButler mode. If a workflow has explicitly left GitButler mode to
use physical git worktrees, mark raw worktree commands with
`GEST_VCS_EXECUTION=git-worktrees`.

For non-trivial completed leaf tasks, add a Gest task note before completion:

```bash
gest task note add <task-id-or-prefix> --agent codex --body "Done: ...\nVerification: ...\nFollow-up: ..."
gest task complete <task-id-or-prefix> --quiet
```

Use task metadata for machine-queryable facts, not prose work logs.

## Commit Cadence

Committing is VCS hygiene, not a Gest task by itself. Do not create a Gest task
whose only purpose is making a normal commit.

Session work should not commit every small leaf by default. Commit when the user
asks, when a coherent checkpoint helps, or when a long-lived parent/subtree
reaches a stable point.

Session classification alone is not a reason to skip `gcm`. A verified slice is
a commit-required checkpoint when it changes deployment/runtime configuration,
persistence, migrations, schemas, public APIs, user-visible UI, reusable
workflow material, publishable docs/templates, or a non-trivial multi-file
changeset. After verification and review, run `git status --short --branch`
before final response. If it shows Codex-owned changes and a commit-required
trigger applies, route through `gcm` before completing the handoff. If `gcm` is
intentionally skipped despite a dirty worktree, record the concrete no-commit
reason in the Gest note and final response.

Development work should commit at verified durable checkpoints such as a
completed depth-1 workstream, coherent depth-2 implementation subtree, handoff,
risky bug/migration fix, or GitHub issue/PR sync.

Stage explicit files and do not put Gest IDs in commit messages.

For development-mode implementation, agents should make the commit judgment
themselves after each verified coherent depth-2 slice instead of only asking the
user at the end. Prefer a commit before moving to the next slice when the work
changes schema, persistence, query semantics, public APIs, user-visible UI, or
non-trivial verification. Use the completed Gest notes to write detailed commit
bodies with what changed, verification run, and real follow-ups. Keep commits
narrow enough that a future `git bisect` lands on a useful layer, not an entire
multi-layer feature. Never include Gest IDs in commit messages.

After every Codex-created commit, make the push/sync decision explicit. Run
`git status --short --branch`; if the user has not asked for local-only work,
push the checkpoint. If the branch has no upstream, set one with
`git push -u origin <branch>` or the repo's equivalent; "no upstream" is not a
reason to stop locally. Do not confuse GitHub issue promotion with `git push`.
A checkpoint is not complete if the branch is silently local or `ahead` of its
upstream.
When Codex pushes changes to a branch other than the repository's mainline
branch, it must create or update the pull request for that branch, run `gpa` on
the PR, report the PR review findings/state to the user, and ask whether to
merge. Do not merge unless the user explicitly asked for that merge in the
current turn or gives approval after the `gpa` review packet. For reusable
workflow/template repo changes, push and PR creation are mandatory unless
blocked; record the exact blocker instead of silently stopping at push.

After merging a PR, check the repository instructions and command contract for
deployment or release steps. If the project defines a deploy/release command
for the merged change, run it or record the exact blocker before handoff.

At every durable checkpoint, run checkpoint hygiene. Durable checkpoints include
any Codex-created Git commit, closing a depth-1 task/product parent, completing
an iteration, or handing off after substantial implementation. Regenerate the
overall Gest graph and a focused graph for the latest relevant iteration; treat
graph generation like a Gest database operation and do not run it in parallel
with `gest` commands. For user-visible, architecture-relevant, multi-session, or
release-worthy work, decide whether to promote/sync a GitHub issue with `gpr`.
For every development depth-1 parent and development iteration, the `gpr`
decision is mandatory: create/sync the GitHub issue and store `github.issue` /
`github.url`, or record why it was not promoted. After every code change, run an
explicit review pass with `grv` or code-review stance before completing the
task. Treat missing focused tests for changed callable code or APIs as review
findings. Report graph paths, commit hashes, push status, review status, and
the GitHub issue decision.

When a Gest-tracked branch becomes a pull request, use `gpa` to review the PR as
an integration checkpoint before approval or merge. The PR should include a Gest
context appendix with parent task, leaf tasks, iteration, artifacts/specs,
verification, follow-ups, and graph links when that context is safe to expose.

## Project Command Contract

Prefer a `Justfile` as the stable executable interface when present. Replace
these placeholders with the project-specific mappings and arguments:

```bash
<setup command>
<format command or just fmt [path]>
<lint command or just lint [path]>
<typecheck command or just typecheck>
<static/compile command or just static>
<build command or just build>
<focused test command or just test [target]>
<full test command or just test>
<smoke command or just smoke>
<run app command or just dev [port]>
<browser setup command or just browser-setup>
<browser spot check command or just browser [url-or-flow]>
<browser integration command or just integration [flow]>
<docs command or just docs>
git diff --check
```

Document command arguments here. For `just`, target parameters are passed
positionally, for example `just lint src/foo.ts`, `just test tests/foo.test.ts`,
or `just dev 3000`.

When changing Just recipes, consult the Just manual rather than treating it like
Make. The key reference for recipe ordering is:

- Just dependencies: https://just.systems/man/en/dependencies.html
- Just skill reference: https://raw.githubusercontent.com/casey/just/refs/heads/master/skills/just/SKILL.md

For Just, dependency order is meaningful: dependencies run before the recipe
that depends on them, and in the listed order. Use native recipe dependencies
when one recipe is an ordered composition of other recipes, such as
`verify: lint typecheck static test smoke diff-check`. Dependencies with the
same arguments run once per `just` invocation. This is ordered recipe
composition, not Make-style file freshness analysis.

Use `gfm` for formatting, linting, typechecking, compile/static checks, and
diff hygiene. Use `gte` for unit tests, API regression tests, smoke checks, and
integration tests. Use `gdo` to check and update user-facing docs,
developer-facing docs, and in-code docs.

Recommended test layout:

- `tests/`: inner-function and focused callable-code unit tests.
- `regression_tests/`: bug and API regression tests.
- `integration_tests/`: end-to-end and browser-agent-driven checks. Repeated
  browser-agent flows should become rerunnable shell scripts here.

For frontend, browser UI, or interaction changes, use the `agent-browser` skill
or the mapped browser spot-check command to inspect the running app visually and
exercise the relevant interaction flow. Do this in addition to code checks so
visual regressions and broken browser gestures are caught before handoff.
If browser-agent verification cannot be completed, say exactly why in the final
response and do not imply the interaction was checked.

Browser spot checks are exploratory implementation checks. Browser integration
tests are durable rerunnable checks; put repeated browser-agent flows under the
project's integration test location.
