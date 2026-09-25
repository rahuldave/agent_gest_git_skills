# Integration branches, review, and delivery

## Branch roles

The repository default branch (often `main`) is its normal mainline. A persistent
integration branch gathers an experiment or release line across many tasks.
Both receive changes through reviewed pull requests. A temporary topic branch
contains one reviewable change; a stack contains dependent topic branches.
Branch roles are explicit policy, never inferred from a name or prefix.

Before editing, resolve the repository default branch, the user's selected
integration target, and its current remote SHA. Project instructions may already
select the target. Create the topic from that target and direct its PR back
there. Record:

```text
vcs.default_branch=<repository default>
vcs.integration_branch=<persistent target>
vcs.base_branch=<immediate PR base>
vcs.base_sha=<resolved starting base commit>
vcs.branch_role=topic|stack-topic|integration
vcs.branch=<work branch>
vcs.integration_sha=<resolved integration commit>
```

For an ordinary topic, base and integration branch are equal. Do not default to
`main` merely because it is the repository default. Keep both mainline and
persistent integration branches buildable; do not develop by pushing work
directly to either. Creating a new persistent branch at an existing reviewed
commit establishes a target; it does not require an empty PR. Publishing that
branch does not imply opening a PR from the whole experiment into mainline.
Promotion from experiment to mainline is a separately scoped and authorized PR.

The project's branch prefix takes precedence over examples in these skills.
Internal worker branches may be integrated into the owning topic locally and
retired without separate remote PRs when their changes are included in that
topic's review. Record this integration; never use it to bypass the target PR.

## Dependent stacks and parallel work

Use a normal topic PR for a coherent change. Use a stack when dependent slices
benefit from separate review. The bottom PR targets the selected integration
branch; each higher PR targets its immediate predecessor. Record
`vcs.stack_root`, `vcs.stack_parent`, and `vcs.stack_index` alongside the common
integration target. Merge bottom-up. After each merge, inspect actual GitHub
base/head state, retarget or restack as needed, and rerun affected checks and
review before merging the next slice. Do not delete a predecessor while child
PRs still depend on it.

In GitButler, inspect the installed CLI's target configuration and PR state;
explicitly set the chosen remote integration target before creating a stack.
Do not assume its remote default is the intended target. Use `but` write
commands while it owns the workspace. GitButler stacks share a checkout;
parallel writers need separate physical worktrees, later integrated deliberately.

## Independent adversarial review

Substantial code, executable setup, CI, and reusable workflow changes require
independent adversarial review before recommending merge. Give a reviewer the
requirements, scope, actual base/head commits, diff, and verification evidence.
Ask them to seek counterexamples, missing tests, regression paths and unsafe
workflow outcomes. They should not implement the change they are reviewing.
Independent read-only subagents are suitable when available and authorized.
Self-review is useful but must be labeled as such; if no independent reviewer
is available, report that gap and hold the merge recommendation.

Record reviewer identity, `review.base_sha`, `review.head_sha`, scope, findings,
and disposition of each finding: fixed with evidence, rejected with reasoning,
or explicitly accepted as residual risk. Fixes need review of the changed
portion and affected contracts at the new head. Base changes require assessing
the new integration context and refreshing affected checks/review. A prior
clean review does not silently transfer to new commits. CI success is separate
from review. Human authorization to merge remains separate from both.

GitHub PR authors cannot approve their own PR. An independent agent using the
author's GitHub account can supply review evidence, but cannot count as a
different GitHub approver. Configure rules to reflect the actual team; never
invent an approval or bypass a required reviewer.

## CI and delivery contract

GSU records commands and triggers; GTE verifies behavior and failure paths; GPA
checks the exact PR's results. Every supported target gets PR checks. Avoid
base/path filters that prevent a required workflow from reporting. If jobs are
conditional, a stable required summary job must run with `always()` and fail
unless all expected jobs succeeded. A skipped test is not passing evidence.
Verify integration pushes as well where required by the project contract.

Use pinned dependencies and documented tool versions. Map relevant boundaries:
static checks, focused tests, integration tests, build/package validation, and
clean installation. Exercise a non-default integration target in workflow labs.
Keep credentialed, paid, or externally destructive checks explicit and opt-in;
ordinary untrusted PR jobs receive no publication credentials. Preserve evidence
and document which platform or live checks remain outside automatic coverage.

Delivery is a separate policy with three possible milestones:

1. Reviewed source integrated into the selected branch.
2. Installable snapshot/artifacts built and checked at an exact commit.
3. Versioned release published and independently verified.

A merge into an experimental branch normally reaches the first milestone and
may reach the second; it does not authorize publishing a stable release. Record
the actual target's post-merge contract rather than running a generic deploy
command unconditionally. For a skill package, validate the manifest and local
references, test installation into an existing project, record source revision,
and publish any requested version/tag only from checked content. A project may
use a protected tag/manual release job; protect its credentials and verify the
resulting artifacts. Do not call source-only delivery a package release.

## Issues and task completion

Promote durable initiatives and independently deliverable features to GitHub;
keep small execution leaves in Gest. Link each PR to the relevant issue and
store issue/PR URLs back in Gest. Define the issue's completion target up front:
experimental integration, mainline integration, or a published release.

GitHub interprets PR closing keywords only for PRs targeting the repository's
default branch. For a non-default target, use `Refs #N`, an explicit issue link,
and a post-merge issue update. Manually close only when its stated acceptance
scope is complete and that action is authorized. Keep release/initiative issues
open when a slice has merely reached the experiment. Avoid closing footers in
experimental commits that could unexpectedly close an issue on later promotion.

Gest maintains its graphs automatically. Continue creating native hierarchy and
dependency links and inspect `gest iteration graph` when useful. No separate
graph exporter, graph file, or graph-path checkpoint is required.

## Installation and resource ownership

Preserve existing project instructions, hooks, and unrelated settings during
installation. Review configuration conflicts explicitly and test repeat installs.
Record repository URL, exact source commit, and whether the source was dirty;
a mutable branch name alone is insufficient provenance. Refresh installed
skills intentionally and keep mirrored references consistent.

Record owned temporary directories, server processes, ports and child processes.
Use isolated disposable resources for tests. Stop only processes created for the
task, verify they exited, and remove only owned temporary files. Never stop a
user's server to make a test pass or reuse an occupied port silently.

## Merge and cleanup

GPA verifies the intended base, reviewed head/base, checks, finding dispositions,
and existing merge authorization immediately before integration. Preserve user
authorization across turns; ask only when the particular merge is not authorized.
After a confirmed merge, sync the actual integration target, leaving persistent
branches intact. Delete only verified merged temporary topics with no worktree
or stack dependents. Do not apply `--delete-branch` to a persistent experimental
branch when promoting it to mainline. Prefer merging first and deciding cleanup
separately. Report source integration, artifact installation, issue state and
publication state distinctly.

### Retire an owned physical worktree

A physical worktree created for a worker is a separate checkout, not a
GitButler branch lane. Before dispatch, record its absolute path, topic branch,
owner/task, selected integration branch and immediate stack parent (if any),
and which checkout is the primary one to preserve. Its branch is selected by
the project and may be `main` or another persistent target. Use `git worktree
list --porcelain` to reconcile that record; never infer ownership from a path prefix
or delete the primary, an unrelated checkout, or one the user chose to retain.

After the worker finishes, wait for its agent and any processes it started to
exit. Confirm no active task, child worktree, or open stack/PR depends on its
branch. From the owned worktree, inspect `git status --porcelain=v1
--untracked-files=all` and `git status --short --ignored`; account for tracked,
untracked, and valuable ignored files before removing the checkout. Preserve
valuable files deliberately or leave the worktree in place and report why.

Verify that the worker's intended commits reached the selected integration
branch or immediate stack parent before retirement. A normal merge can use
commit ancestry; cherry-picks and squash merges need a reviewed
patch-equivalence/diff judgment because their commit IDs change. An open PR, a
push, or a completed Gest task is not integration evidence. If integration or
dependency state is uncertain, retain the worktree and topic branch.

From another checkout, use `git worktree remove <owned-absolute-path>` without
`--force`, then verify that `git worktree list --porcelain` no longer lists it.
Do not use routine `rm -rf`, forced worktree removal, or pruning to bypass dirty
state. Only afterward retire an eligible temporary topic branch: `git branch
-d <topic>` after verified ancestry, or make an explicit disposal decision
following a verified cherry-pick/squash equivalent; do not force-delete one
automatically when `git branch -d` rejects it. Keep persistent integration
branches, stack parents with dependents, primary branches, and user-retained
worktrees intact. Record what was removed and what remains.

## References

- [GitHub issue linking and non-default targets](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue)
- [Required checks and skipped workflows](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)
- [GitHub approval restrictions](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/approving-a-pull-request-with-required-reviews)
