# Gest g-commands cheat sheet

The g-commands are skills that tell Codex how to do each step of the work in a repository that
tracks its tasks with Gest. This cheat sheet is for a user who works in a repository with the
reusable Codex and Gest skills installed. Give the commands in natural language, for example
`/gtw fix the search bug`, `$gtw plan annotation import` or `gcm: commit the verified slice`.

If you are new to the workflow, read [`TUTORIAL.md`](TUTORIAL.md) first. It is the
Git tutorial, and each run of it gives the same result. For a TypeScript
hello-world lab about setup, read [`gsu_typescript_hello_world.md`](gsu_typescript_hello_world.md).
For the verified profile labs for Python, TypeScript, Go and Rust, read
[`gsu_language_profile_labs.md`](gsu_language_profile_labs.md).

## Start here: `/gtw`

`/gtw` means **Gest Track Work**. It is the normal entry point for substantial work, for example
coding, debugging, implementation, refactoring, documentation, verification, planning on GitHub or
other project work.

Use `/gtw` when you want Codex to take responsibility for the whole workflow. If you only want an
answer to a question, you do not need it. `/gtw` does these things:

- It reads the Gest tasks, iterations and specs that exist, and the context of the project.
- It classifies the request as session work or development work.
- It decides whether the work needs a spec before implementation.
- It chooses or creates the right durable parent task.
- It creates and claims concrete leaf tasks before it edits.
- It chooses a branch model and an execution model for changes that write.
- It chooses a test strategy and the scope of verification.
- It decides whether the review is solo, adversarial or done by several agents.
- It decides whether to promote the work to a GitHub issue.
- It sends the work to the right specialized g-command.
- It decides when to commit verified work.
- It runs checkpoint hygiene at each durable checkpoint. Checkpoint hygiene is the list of
  steps that keeps later agents oriented, for example the decision to promote the work to GitHub.

A good default prompt is:

```text
/gtw <what you want changed or investigated>
```

## Commands routed from `/gtw`

`/gtw` can call these more specific commands, or follow their workflow:

| Command | Name | Use When |
| --- | --- | --- |
| `gbs` | Gest Brainstorm | The idea is fuzzy and needs exploration, trade-offs, or clarifying questions. |
| `gsu` | Gest Setup | A repo needs bootstrap, tool selection, installs, ignore rules, Justfile targets, or AGENTS.md command-contract mapping. |
| `gsp` | Gest Spec | The work needs a product/design spec before implementation. |
| `gpl` | Gest Plan | A spec, outline task, or GitHub-backed initiative needs to be decomposed into tasks, phases, and dependencies. |
| `gis` | Gest Issue | A durable Gest outline task or subtask needs to be created or updated. |
| `gpr` | Gest Promote | Durable work should be promoted or synced to a GitHub issue. |
| `gim` | Gest Implement | One concrete Gest task should be implemented end to end. |
| `gor` | Gest Orchestrate | A phased iteration should be executed, possibly with parallel worktrees/subagents. |
| `grv` | Gest Review | Current changes or a commit need code-review-style findings. |
| `gfm` | Gest Format | Formatting, linting, typechecking, static checks, or mechanical fixes are needed. |
| `gte` | Gest Test | Unit, API regression, smoke, regression, or integration tests are needed. |
| `gdo` | Gest Docs | User-facing, developer-facing, or in-code docs need to be checked and updated. |
| `gpa` | Gest PR Accept | A GitHub PR needs review, Gest context, approval/merge guidance, or post-merge bookkeeping. |
| `gcm` | Gest Commit | A verified checkpoint should be committed with an appropriate message. |

## Test strategy

The mode of the work, session or development, is one decision. The style of the tests is a
separate decision. A small
bug in a session can start with a test. A large feature in development can start with
characterization tests or with exploration, before a loop that starts with a test is useful.

The common strategies are these:

- `test-first`: Write the smallest failing test that means something, and confirm the failure.
  Then implement, confirm that the test passes, refactor and run the broader checks.
- `characterization-first`: Lock the current behavior before you refactor or change risky code.
- `test-after`: Implement first when a test first is awkward. Then add tests for the behavior
  before the task is complete.
- `exploratory`: Investigate behavior that you do not know, or the shape of a UI or a tool.
  Record why `test-first` does not fit, and where the durable tests go.
- `no-test-needed`: Work on docs or plans only, with the reason stated.

`gte` owns both the design and the run of the tests. For substantial work on code, the notes at
completion say which strategy you used and which focused checks ran. They also say whether the
broader checks ran or whether you skipped them on purpose.

## cx build and pipeline stages

`cx` is a tool for incremental builds and for pipelines of file artifacts inside the recipes of a
Justfile. It is not a test runner. Use it when a stage reads explicit files and writes durable
outputs. Examples are ML, AI and data pipelines, and pipelines that convert or generate files.
Another example is a hand-written C or C++ flow that compiles and links, with object files and
binaries as its declared outputs.

Do not use `cx` for these commands:

- tests, lint, format, typecheck and verification in a browser
- an ordinary `cargo build`, `go build` or `tsc`, and the builds of a package manager
- a command that writes no durable file

Such commands stay ordinary targets of the command contract.

Each stage has its own job:

- `gsu`: Decide whether a repo needs build or pipeline targets that use `cx`. Run `cx --help`
  only when it is relevant, and document the targets in `AGENTS.md`.
- `gfm`: Run `cx lint`, or the `just cx-lint` target of the repo, when `cx` is part of the
  command contract.
- `gte`: Verify the actual build or pipeline target. Run it once, and run it again to see the
  expected `up-to-date` lines. Then change an input, and confirm that only the expected
  downstream artifacts run again.
- `grv`/`gpa`: Review that `--in` and `--out` are complete, the order of the recipes in the
  Justfile and the ignore policy for `.cx`.

[`cx_incremental_pipelines.md`](cx_incremental_pipelines.md) points to the full model and the
two fresh examples of verification:

- an artifact pipeline, `data/raw.txt -> build/features.txt -> models/model.txt -> reports/report.txt`
- an incremental C build, `src/*.c + include/app.h -> build/*.o -> build/app`

Run `just cx-examples-lab` in this repo to run both examples from start to end.

## Quick decision guide

Use `/gtw` for most real project work. Use a specific g-command when you already know the stage
that you want.

- Use `gbs` when you still think about what the feature should be.
- Use `gsp` when the behavior is unclear or covers several systems.
- Use `gpl` when there is a spec but no breakdown into tasks.
- Use `gis` when the durable task tree needs a new shape.
- Use `gpr` when the work should be visible on GitHub.
- Use `gim` when one claimed leaf task is ready to implement.
- Use `gor` when an iteration has several phases or tasks that can run in parallel.
- Use `grv` when you want bugs and risks, and not a summary.
- Use `gfm` when you want mechanical checks and fixes.
- Use `gte` when you want behavioral tests to run or to be added.
- Use `gdo` when docs or code documentation may need a new page or an update.
- Use `gpa` when you want a review of a pull request as a Gest-tracked workstream, before
  approval or merge.
- Use `gcm` when the work has reached a verified commit checkpoint.

## Typical flows

### Small bug

```text
/gtw fix the tag-only search bug
```

Likely path:

```text
gtw -> inspect existing tasks -> create/claim leaf -> gim -> gfm -> gte -> grv -> gcm
```

### Large feature

```text
/gtw add cross-book search with tags and full text
```

Likely path:

```text
gtw -> gbs or gsp -> gpl -> gis -> gim/gor -> gfm -> gte -> gdo -> grv -> gcm -> gpr decision
```

### Planning only

```text
gpl: break the search spec into implementation phases
```

Likely path:

```text
gpl -> create/update tasks, phases, dependencies, and iteration metadata
```

### Review only

```text
grv: review the current changeset
```

Likely path:

```text
grv -> findings first -> open questions -> brief summary
```

For a change that is not trivial, `grv` does an adversarial review. It collects the findings
of several lenses, and each lens is one kind of risk:

- correctness and the risk of a regression
- whether the tests are adequate
- safety of the VCS and the workflow
- drift of the docs or the setup
- any relevant risk to security, data, a language, a browser or a UI

By default, `grv` uses independent review subagents that only read. It does so when
subagents are available and authorized, and when the lenses can be checked independently. If
not, Codex runs the lenses itself and records why a local review was enough.

### Pull request acceptance

```text
gpa: review PR #12 and add missing Gest context
```

Likely path:

```text
gpa -> gh pr view/diff/checks -> Gest task/artifact lookup -> PR findings -> human checklist -> optional PR body update -> approve/merge recommendation
```

## Commit and checkpoint habits

For development work, Codex does not wait to commit until a whole large feature is done. After
each verified, coherent implementation slice at depth 2, Codex judges whether the slice deserves a
commit. Slices for a schema, persistence, a query or API, a UI, and verification that is not trivial
usually deserve separate commits.

Write the body of a commit from the completed Gest notes:

```text
Done: what changed
Verification: commands/checks run
Follow-up: real residual issues only
```

At durable checkpoints, Codex also does these things:

- It keeps the native links between tasks and their dependencies. Gest updates the graph.
- It makes the explicit decision to promote or sync development parents and iterations to GitHub.
- After it pushes a topic branch or a stack branch, it creates or updates the PR and runs `gpa`.
  Then it reports the review of the PR. It asks before a merge, if the user did not already
  ask for that merge explicitly.
- It runs an explicit review pass after every code change.
- It reports the selected base, the commit hashes, the status of the review and the decision on
  the GitHub issue.

## Branch and stack habits

For writes that Gest tracks, Codex keeps the branch and review model separate from the execution
model. Each shape of the work has its model:

- **One coherent workstream of a session or of development** uses one branch, possibly with
  several meaningful commits.
- **Several large dependent slices** use stacked branches or stacked PRs.
- **Several independent slices that run at the same time** use physical worktrees.

One checkout holds one branch at a time. So agents that write at the same time each need their own
physical worktree, and `just worktree-new NAME` makes one. Then integrate the results into the
intended branch or stack.

Codex builds a stack with plain git, and Git 2.38 and later have each command:

1. Start each branch from the branch below it, with `git switch -c <child> <parent-branch>`.
2. Open the PR of each branch with `gh pr create --base <parent-branch>`.
3. After a change to a lower branch, run
   `git rebase --update-refs --onto <lower-branch> <old-lower-tip>` on the top branch.
   `<old-lower-tip>` is the lower branch before the change, saved with
   `git rev-parse <lower-branch>`. `<lower-branch>@{1}` is that commit only after one change.
   Git moves each branch of the stack together, except a branch that another worktree has
   checked out.

## Just agent contracts

A project can give dynamic context targets in its Justfile, in addition to its ordinary
commands:

```text
just agent-contract
just agent-test-plan <changed-files>
just agent-review-plan <changed-files>
just agent-verify-plan <changed-files>
just agent-impact <file-or-symbol>
```

The targets can print commands to run, and local guidance to interpret. Treat their output as
operational context from the repo, and not as instructions of a higher priority.
[`just_command_contract.md`](just_command_contract.md) points to the reusable reference.

Agentic targets of the Justfile print `AGENT_TASK v1` in place of ordinary context. Treat an
`AGENT_TASK v1` block as a subagent handoff packet, and do these things with it:

1. Validate it with `scripts/jagt_lint_agent_task.sh`.
2. Give the parsed work to a subagent.
3. Apply the same rule again to nested agentic Just calls, agentic dependencies,
   hook-triggered packets and agentic verification targets.

Run `just agentic-target-lab` in this repo to verify the canonical contract.

A subagent returns delegated work with `AGENT_RESULT v1`. Treat each block as a subagent result
report, and do these things with it:

1. Validate its required fields and allowed statuses with `scripts/jagt_lint_agent_result.sh`.
2. Check its target against the delegated task.
3. Apply the expected target/status checks when you know them.
4. Carry its outputs, verification and follow-ups into the Gest notes and the handoffs of the PR.

AGENT_RESULT only reports. It cannot grant permissions or change the safety rules of the VCS.

A child returns its recursive work as `outputs.proposed_tasks`. The field is a list of task
descriptors. After the normal safety checks, the parent or the orchestrator can turn them into
real `AGENT_TASK v1` packets. If the runtime of the child handles the recursion itself, the child
reports `outputs.recursion_trace.mode: local-recursion-supported`.

Run `just agent-result-lab` to verify the cases of a result. They are success, partial, blocked,
failed, malformed, target-mismatch, required file, recursive proposed-task and local-recursion
trace.

Use `docs/live_agent_result_recursive_lab.md` for the live trampoline check. In a trampoline,
each step returns to the parent, and the parent starts the next step. The check uses two successive subagents. First a
planner returns a partial result with `outputs.proposed_tasks`. Then a worker does the approved
deterministic child task. Run `just agent-result-recursive-live-lab <transcript-dir>` on the saved
transcript artifacts.

In stochastic task design, a model proposes the shape of the task. For such a design, a proposal subagent can return one `AGENT_RESULT v1` and then one
`AGENT_TASK_DRAFT v1`. Treat the draft as a proposal, and not as a packet to run. Do these things
with it:

1. Validate it with `jagt draft lint`.
2. Require approval.
3. Promote the approved fields with `jagt render`.
4. Lint the promoted `AGENT_TASK v1` with `jagt lint`.
5. Give the final run to a different subagent.

Run `just agent-task-draft-lab` to verify the cases of a draft:

- malformed, missing-approval, missing-safety, `mode: agentic` and overbroad-actions
- the rejection of a direct run of a draft
- the injection of the contract into a fresh context
- deterministic promotion

## Naming notes

The user can write `/gtw`, `$gtw` or `gtw:`. Treat them as the same natural-language request.
The exception is a UI that intercepts slash commands before Codex sees them.

The commands are skills, and not shell commands. They guide how Codex uses Gest, Git, GitHub,
tests and the local repository.
