# Git tutorial

This tutorial creates four temporary GitHub repositories with fixed names, and it runs four
agent workflows in them. After each turn of the agent, it tells you what to check. The
steps for pull requests (PRs) first create the PRs. A later step merges them, and then the
cleanup deletes the temporary repositories.

You learn these review shapes and checks:

1. ordinary git branch PR
2. ordinary git multi-commit PR
3. stacked PRs with plain git for dependent slices
4. physical git worktrees for independent parallel slices
5. tag classification and ast-grep dependency checks before code edits

Every step uses plain git and `gh`.

## Pull request command map

The tutorial creates its PRs with these commands:

- Step 1: `gh pr create --base main --head tutorial/plain`
- Step 2: `gh pr create --base main --head tutorial/multi`
- Step 3: `gh pr create --base main --head tutorial/stack-base`, then
  `gh pr create --base tutorial/stack-base --head tutorial/stack-child`
- Step 4: `gh pr create --base main --head tutorial/worktree-a` and
  `gh pr create --base main --head tutorial/worktree-b`

A stack is a chain of branches, where each branch starts from the branch below it. Open the PRs
of a stack from the bottom branch up. Give each PR the branch below it as its base, with
`gh pr create --base <parent-branch>`. Then each PR shows only the change of its own branch.

## What the tutorial does

The agent creates these GitHub repositories under your GitHub account, and it deletes them
later:

```text
agent-gest-git-tutorial-plain
agent-gest-git-tutorial-multi
agent-gest-git-tutorial-stack
agent-gest-git-tutorial-worktrees
```

Do not use these names for anything valuable. Before the agent starts, the prompts below tell it
to delete each repository that has one of these names. The cleanup deletes them again with
`gh repo delete --yes`.

Before you start, make sure of these things:

- `gh auth status -h github.com` succeeds.
- Your GitHub auth has the `repo` and `delete_repo` scopes.
- `git` 2.38 or later, `gh`, `gest` and `just` are installed.
- You agree that the agent creates and deletes the four temporary repositories above.

## Step 0: Setup and cleanup contract

What this step teaches:

The agent uses fixed names for the repositories, and it cleans up before and after the
tutorial. It also tells you where it wrote the logs.

Ask the agent:

```text
Run the Git tutorial setup.

Use my GitHub account from `gh api user -q .login`.
Use exactly these temporary private repo names:

- agent-gest-git-tutorial-plain
- agent-gest-git-tutorial-multi
- agent-gest-git-tutorial-stack
- agent-gest-git-tutorial-worktrees

Before starting, delete any existing GitHub repos with those names using
`gh repo delete <owner>/<name> --yes`, ignoring "not found" errors.

Create a local tutorial root at `/tmp/agent-gest-git-tutorial`.
Create `/tmp/agent-gest-git-tutorial/logs`.

For each following step, write a command log in that logs directory. After the
PR-opening steps finish, merge the PRs in Step 6. After the merge step, delete
the four GitHub repos unless I explicitly ask to keep them.
```

After the agent finishes, check:

```bash
test -d /tmp/agent-gest-git-tutorial/logs
```

The agent reports your GitHub owner and the exact directory of the logs.

## Step 1: Ordinary git branch PR

What this step teaches:

Use ordinary git for one simple review branch.

Repository:

```text
agent-gest-git-tutorial-plain
```

Ask the agent:

````text
Run tutorial step 1: ordinary git branch PR.

Create private GitHub repo `agent-gest-git-tutorial-plain`.
Clone or initialize it under `/tmp/agent-gest-git-tutorial/plain`.
Create `main` with README.md containing `plain tutorial base`.
Push `main`.

Create branch `tutorial/plain` with ordinary git.
Add `plain.txt` containing `plain branch change`.
Commit with message `test: add plain branch change`.
Push the branch.
Open a PR:

```bash
gh pr create \
  --repo "$(gh api user -q .login)/agent-gest-git-tutorial-plain" \
  --base main \
  --head tutorial/plain \
  --title 'test: plain git branch flow' \
  --body 'Tutorial plain git branch flow.'
```

Write all commands and key outputs to
`/tmp/agent-gest-git-tutorial/logs/01-plain-git-branch.log`.
````

After the agent finishes, check:

```bash
gh pr view tutorial/plain \
  --repo "$(gh api user -q .login)/agent-gest-git-tutorial-plain" \
  --json state,baseRefName,headRefName,title
```

Expected:

```text
state: OPEN
baseRefName: main
headRefName: tutorial/plain
title: test: plain git branch flow
```

Commands that the agent should use:

- `git checkout -b tutorial/plain`, or another ordinary git command that creates the branch
- `git commit`
- `git push`
- `gh pr create`

## Step 2: Ordinary git multi-commit PR

What this step teaches:

Use ordinary git when one review branch needs more than one commit.

Repository:

```text
agent-gest-git-tutorial-multi
```

Ask the agent:

````text
Run tutorial step 2: ordinary git multi-commit PR.

Create private GitHub repo `agent-gest-git-tutorial-multi`.
Clone or initialize it under `/tmp/agent-gest-git-tutorial/multi`.
Create `main` with README.md containing `multi tutorial base`.
Push `main`.

Create branch `tutorial/multi` with ordinary git.
Add `session.txt` containing `session edit one`.
Commit with message `test: add first session edit`.
Append `session edit two` to `session.txt`.
Commit with message `test: add second session edit`.
Push the branch.
Open a PR:

```bash
gh pr create \
  --repo "$(gh api user -q .login)/agent-gest-git-tutorial-multi" \
  --base main \
  --head tutorial/multi \
  --title 'test: multi commit git branch flow' \
  --body 'Tutorial multi-commit git branch flow.'
```

Write all commands and key outputs to
`/tmp/agent-gest-git-tutorial/logs/02-multi-commit-git-branch.log`.
````

After the agent finishes, check:

```bash
owner="$(gh api user -q .login)"
gh pr view tutorial/multi \
  --repo "$owner/agent-gest-git-tutorial-multi" \
  --json state,baseRefName,headRefName,title,commits
```

Expected:

```text
state: OPEN
baseRefName: main
headRefName: tutorial/multi
title: test: multi commit git branch flow
commits: two commits on the PR branch
```

## Step 3: Stacked PRs with plain git

What this step teaches:

Use a stack when you have several large slices that depend on each other, and each slice needs
its own review. Each branch of the stack starts from the branch below it, and each PR targets
the branch below it.

Repository:

```text
agent-gest-git-tutorial-stack
```

Ask the agent:

````text
Run tutorial step 3: stacked PRs with plain git.

Create private GitHub repo `agent-gest-git-tutorial-stack`.
Clone or initialize it under `/tmp/agent-gest-git-tutorial/stack`.
Create `main` with README.md containing `stack tutorial base`.
Push `main`.

Create branch `tutorial/stack-base` from `main`.
Add `stack.txt` containing `stack base`.
Commit with message `test: stack base flow`.

Create branch `tutorial/stack-child` from `tutorial/stack-base`.
Append `stack child` to `stack.txt`.
Commit with message `test: stack child flow`.

Change the lower branch once, to show how the stack moves together:
switch to `tutorial/stack-base`, add `base-note.txt` containing `base note`,
and commit with message `test: add base note`. Then switch to
`tutorial/stack-child` and run:

```bash
git rebase --update-refs --onto tutorial/stack-base 'tutorial/stack-base@{1}'
```

`tutorial/stack-base@{1}` is the lower branch before the new commit.

Push both branches.
Open the two PRs from the bottom branch up:

```bash
owner="$(gh api user -q .login)"
gh pr create \
  --repo "$owner/agent-gest-git-tutorial-stack" \
  --base main \
  --head tutorial/stack-base \
  --title 'test: stack base flow' \
  --body 'Tutorial stack base flow.'
gh pr create \
  --repo "$owner/agent-gest-git-tutorial-stack" \
  --base tutorial/stack-base \
  --head tutorial/stack-child \
  --title 'test: stack child flow' \
  --body 'Tutorial stack child flow.'
```

Write all commands and key outputs to
`/tmp/agent-gest-git-tutorial/logs/03-stacked-prs.log`.
````

After the agent finishes, check:

```bash
owner="$(gh api user -q .login)"
gh pr list \
  --repo "$owner/agent-gest-git-tutorial-stack" \
  --state open \
  --json title,baseRefName,headRefName
```

Expected:

```text
PR: test: stack base flow
baseRefName: main
headRefName: tutorial/stack-base

PR: test: stack child flow
baseRefName: tutorial/stack-base
headRefName: tutorial/stack-child
```

Commands that the agent should use:

- `git switch -c tutorial/stack-base main`
- `git switch -c tutorial/stack-child tutorial/stack-base`
- `git commit`
- `git rebase --update-refs --onto tutorial/stack-base 'tutorial/stack-base@{1}'`, after a
  change to the lower branch
- `git push`
- `gh pr create --base main` for the bottom PR, and
  `gh pr create --base tutorial/stack-base` for the child PR

The `--update-refs` option needs git 2.38 or later. With it, a rebase of the top branch also
moves each branch below it that the rebase passes. The step does not use physical git worktrees.

## Step 4: Physical git worktrees

What this step teaches:

Use physical git worktrees for independent slices that run in parallel. A physical worktree is
a separate folder with its own checkout of a branch. Give each agent that writes its own
worktree, so that two agents never write in one folder.

Repository:

```text
agent-gest-git-tutorial-worktrees
```

Ask the agent:

````text
Run tutorial step 4: physical git worktrees.

Create private GitHub repo `agent-gest-git-tutorial-worktrees`.
Clone or initialize it under `/tmp/agent-gest-git-tutorial/worktrees`.
Create `main` with README.md containing `worktree tutorial base`.
Push `main`.

Create two physical git worktrees:
- `/tmp/agent-gest-git-tutorial/worktree-a` on branch `tutorial/worktree-a`
- `/tmp/agent-gest-git-tutorial/worktree-b` on branch `tutorial/worktree-b`

In worktree A, add `worktree-a.txt` containing `worktree a isolated change`,
commit with message `test: add worktree a change`, push the branch, and open a
PR:

```bash
gh pr create \
  --repo "$(gh api user -q .login)/agent-gest-git-tutorial-worktrees" \
  --base main \
  --head tutorial/worktree-a \
  --title 'test: worktree a flow' \
  --body 'Tutorial physical worktree A flow.'
```

In worktree B, add `worktree-b.txt` containing `worktree b isolated change`,
commit with message `test: add worktree b change`, push the branch, and open a
PR:

```bash
gh pr create \
  --repo "$(gh api user -q .login)/agent-gest-git-tutorial-worktrees" \
  --base main \
  --head tutorial/worktree-b \
  --title 'test: worktree b flow' \
  --body 'Tutorial physical worktree B flow.'
```

Remove both physical worktrees after the PRs are open.

Write all commands and key outputs to
`/tmp/agent-gest-git-tutorial/logs/04-physical-worktrees.log`.
````

After the agent finishes, check:

```bash
owner="$(gh api user -q .login)"
gh pr list \
  --repo "$owner/agent-gest-git-tutorial-worktrees" \
  --state open \
  --json title,baseRefName,headRefName
```

Expected:

```text
PR: test: worktree a flow
baseRefName: main
headRefName: tutorial/worktree-a

PR: test: worktree b flow
baseRefName: main
headRefName: tutorial/worktree-b
```

Commands that the agent should use:

- `git worktree add ...`
- ordinary `git commit` inside each physical worktree
- `gh pr create`

What the agent should not do:

- run two agents that write in one folder

## Step 5: Tags and ast-grep dependency check

What this step teaches:

Before the agent edits code, it classifies the task with the tags of the project. A tag is a
label on a Gest task that names a concern of the code. The agent also runs ast-grep, a tool that
searches code by its syntax, on the semantic contract that the change touches. If another
surface depends on that contract, before implementation the agent expands the task, or
creates a child task with the same tag.

The step is a live lab in a local TypeScript repository. It shows two different signals of a
dependency:

- tag dependency: Gest tasks that already have a tag for the same semantic concern
- ast-grep dependency: TypeScript call sites that use the function that changes

Local fixture:

```text
/tmp/agent-gest-git-tutorial/tag-ast-grep-live
```

If you run the tutorial from this repository of reusable skills, one command does the whole
step:

```bash
scripts/run_tag_dependency_typescript_lab.sh \
  /tmp/agent-gest-git-tutorial/tag-ast-grep-live \
  /tmp/agent-gest-git-tutorial/logs/05-tag-ast-grep.log
```

Ask the agent:

````text
Run tutorial step 5: live TypeScript tag and ast-grep dependency lab.

Create or replace `/tmp/agent-gest-git-tutorial/tag-ast-grep-live`.
Initialize it as a git repo and a local Gest project.
Create `/tmp/agent-gest-git-tutorial/logs/05-tag-ast-grep.log`.

In Gest, create these existing tasks and tags:

- `Shared count/probability color contract`
  - tags: `count-or-probability-coloring`, `design`
- `Render histogram bin colors`
  - tags: `count-or-probability-coloring`, `histogram-colors`
- `Render probability pill colors`
  - tags: `count-or-probability-coloring`, `probability-pill-colors`
- `Polish reader hover affordance`
  - tags: `reader-ui`

Collect the existing tag vocabulary from Gest before choosing tags:

```bash
gest task list --all --json
gest artifact list --all --json
gest iteration list --all --json
```

Create a small TypeScript project with:

- `src/colors.ts`, exporting `countOrProbabilityColorScale`
- `src/histogram.ts`, calling `countOrProbabilityColorScale`
- `src/pill.ts`, calling `countOrProbabilityColorScale`
- `src/readerHover.ts`, not calling `countOrProbabilityColorScale`

Run `npm install` and `npm exec -- tsc --noEmit`.

Before editing anything, classify the requested change "change histogram colors
for low-count bins" against the Gest vocabulary:

- selected existing tag: `count-or-probability-coloring`
- selected existing tag: `histogram-colors`
- selected existing tag: `probability-pill-colors`
- rejected near miss: `reader-ui`
- new dynamic tags: none

Then run:

```bash
ast-grep run \
  --lang typescript \
  --pattern 'countOrProbabilityColorScale($$$)' \
  --json=compact \
  src
```

The tag dependency expansion should show the histogram and probability-pill
tasks are linked by `count-or-probability-coloring`. The ast-grep dependency
expansion should find both `src/histogram.ts` and `src/pill.ts`, and it should
not match `src/readerHover.ts`.

Write the selected tags, rejected tag, new-tag decision, tag-linked work,
ast-grep command, matched files, non-matched reader file, and dependency-impact
conclusion to `/tmp/agent-gest-git-tutorial/logs/05-tag-ast-grep.log`.
````

After the agent finishes, check:

```bash
rg "tag dependency expansion|ast-grep dependency expansion|count-or-probability-coloring|src/histogram.ts|src/pill.ts|src/readerHover.ts|reader-ui" \
  /tmp/agent-gest-git-tutorial/logs/05-tag-ast-grep.log
```

Expected:

```text
tag dependency expansion
ast-grep dependency expansion
count-or-probability-coloring
src/histogram.ts
src/pill.ts
src/readerHover.ts
reader-ui
```

The agent reports that an implementation of the histogram colors must also cover the colors of
the probability pill. Or, before completion, it creates a child task with the tag of the same
semantic dependency.

Commands that the agent should use:

- `gest task list --all --json`, `gest artifact list --all --json` and
  `gest iteration list --all --json`, before it chooses tags
- `npm install` and `npm exec -- tsc --noEmit`
- `ast-grep run --lang typescript --pattern 'countOrProbabilityColorScale($$$)'`

What the agent should not do:

- invent "existing" tags before it collects the tag vocabulary of Gest
- use a raw search for a string as the main dependency check, when `ast-grep` supports the
  language

## Step 6: Merge the tutorial PRs

What this step teaches:

A durable checkpoint does not end when the PRs are open. Review and accept each PR before you
merge it. Then merge the PRs before the cleanup. The merge before the cleanup tests the deletion
of branches, the state of the PRs and the order of the stacked PRs.

Ask the agent:

```text
Run tutorial step 6: accept and merge tutorial PRs.

Use my GitHub account from `gh api user -q .login`.

Before merging, record each PR number with `gh pr view <branch> --json number`.
For each PR, run the PR acceptance checkpoint first:

- inspect `gh pr view <number> --json number,url,state,isDraft,title,body,headRefName,baseRefName,mergeable,reviewDecision,commits,files,statusCheckRollup,latestReviews`
- inspect `gh pr diff <number> --patch`
- inspect `gh pr checks <number>`, treating "no checks reported" as an
  explicit state to report, not as a silent pass
- report findings first
- report PR state, checks, branch/base, mergeability, and the exact merge
  recommendation
- stop and ask before merging if there are findings, mergeability is not clean,
  or the PR target/branch shape is not the expected tutorial shape

After explicit merge authorization, merge these PRs with `gh pr merge <number> --merge`, and
verify each PR state is `MERGED` by PR number:

- repo `agent-gest-git-tutorial-plain`, PR branch `tutorial/plain`
- repo `agent-gest-git-tutorial-multi`, PR branch `tutorial/multi`
- repo `agent-gest-git-tutorial-worktrees`, PR branch `tutorial/worktree-a`
- repo `agent-gest-git-tutorial-worktrees`, PR branch `tutorial/worktree-b`

For repo `agent-gest-git-tutorial-stack`, merge in this order:

1. merge PR branch `tutorial/stack-child` into `tutorial/stack-base`
2. merge PR branch `tutorial/stack-base` into `main`

Write all commands and key outputs to
`/tmp/agent-gest-git-tutorial/logs/06-merge-prs.log`.
```

After the agent finishes, check:

```bash
owner="$(gh api user -q .login)"

gh pr list \
  --repo "$owner/agent-gest-git-tutorial-plain" \
  --state merged \
  --search "head:tutorial/plain" \
  --json state,baseRefName,headRefName,title

gh pr list \
  --repo "$owner/agent-gest-git-tutorial-multi" \
  --state merged \
  --search "head:tutorial/multi" \
  --json state,baseRefName,headRefName,title

gh pr list \
  --repo "$owner/agent-gest-git-tutorial-stack" \
  --state merged \
  --json title,baseRefName,headRefName

gh pr list \
  --repo "$owner/agent-gest-git-tutorial-worktrees" \
  --state merged \
  --json title,baseRefName,headRefName
```

Expected:

```text
plain PR: state MERGED, baseRefName main, headRefName tutorial/plain
multi PR: state MERGED, baseRefName main, headRefName tutorial/multi
stack child PR: state MERGED, baseRefName tutorial/stack-base
stack base PR: state MERGED, baseRefName main
worktree A PR: state MERGED, baseRefName main
worktree B PR: state MERGED, baseRefName main
```

Commands that the agent should use:

- `gh pr view <branch> --json number`, before it deletes the branches of the PRs
- `gh pr view <number> --json ...`, `gh pr diff <number> --patch` and
  `gh pr checks <number>`, as the PR acceptance checkpoint before each merge
- `gh pr merge <number> --merge`
- `gh pr view` or `gh pr list --state merged`

What the agent should not do:

- delete the temporary repositories before it verifies that each PR has the state `MERGED`
- delete the stacked branches before it merges the child PR and the base PR of the stack

## Step 7: Cleanup

Ask the agent:

```text
Run tutorial cleanup.

Delete these GitHub repositories if they exist:
- agent-gest-git-tutorial-plain
- agent-gest-git-tutorial-multi
- agent-gest-git-tutorial-stack
- agent-gest-git-tutorial-worktrees

Use `gh repo delete <owner>/<repo> --yes`.
Remove `/tmp/agent-gest-git-tutorial/worktree-a` and
`/tmp/agent-gest-git-tutorial/worktree-b` if they still exist.
Keep `/tmp/agent-gest-git-tutorial/logs` unless I ask you to remove logs.
```

After the cleanup, check one repo:

```bash
owner="$(gh api user -q .login)"
gh repo view "$owner/agent-gest-git-tutorial-plain"
```

Expected:

```text
repository not found
```

## Automated regression labs

The scripts in this repo are regression checks. They are not the beginner tutorial:

```bash
just tag-dependency-live-lab
just language-profile-labs
```

Read this tutorial first. Use the labs when you want to verify the repository of reusable skills.

For this tutorial, `main` is the selected integration target. In an existing project, use the
declared target in every step. The declared target can be a persistent experiment branch.
Clean up only a temporary topic branch that you verified as merged, and that no stack and no
worktree depends on. Keep the persistent branches. For the details, read
[the integration contract](integration_delivery_workflow.md).
