# Spec: Commit gates for any repository

## Problem Statement

The rules for a commit live in the global `CLAUDE.md` file and in `AGENTS.md`
files. They say that a commit needs lint, tests, integration tests, types and
docs checks, and an adversarial review. They also say that the docs of a public
repository go to a website. Nothing checks these rules. An agent can commit
without a review. No record shows what ran.

The parts of a solution exist, but they are not joined:

- **The `just` command contract** of jnterfaces names the recipes `fmt`,
  `lint`, `typecheck`, `test`, `integration` and `verify`. It says not to add a
  recipe that does nothing, so the set of recipes changes from repository to
  repository.
- **The `grv` skill** tells an agent to do an adversarial review. No check
  makes sure that the review happened.
- **The Claude hooks** of agent_gest_git_skills add the commit docs when an
  agent commits. The Codex hooks have no commit hook.
- **GitButler** is in the hooks, skills and docs of agent_gest_git_skills,
  mostly for stacked PRs. The spec drops it.
- **The Python profile** installs the pre-commit framework, which owns
  `.git/hooks/pre-commit` and changes files at commit time.
- **jagt** renders and checks task packets for agents. No recipe uses it for a
  review.

## Terms

| Term | Meaning |
|---|---|
| Gate | A check that stops a commit when it fails. |
| Lab | A test that runs a real scenario in a temporary repository and checks the result. |
| Role | A package of skills that the jnterfaces installer adds to a project, for example `tasker`. |
| Tasker | The role of agent_gest_git_skills. It adds the Gest skills, the hooks and the worktree recipes. |
| Profile | The tools of one language, for example jnprofile-python. |
| Owner | A part of the stack that adds lines or parts to a shared file: jnterfaces, a profile, a tool of a profile, or a role. |
| Worktree tree | The tree hash of all the files in the worktree, staged or not. The section "The worktree tree" says how to compute it. |
| Commit tree | The tree hash of the index at commit time. |
| Log folder | The folder `.agents/log/` of a worktree. Git ignores it. |
| Shared log folder | The log folder of the main checkout. All worktrees of a repository write their packets and records there. |
| Run log | The file `.agents/log/just.jsonl` of a worktree, with one JSON line for each event. |
| Step | One recipe that `just check` runs, for example `lint`. |
| No-op step | A step with no tool in the repository. It logs a skip and does no work. |
| Pass | A line in the run log that says every step passed for one worktree tree. |
| Agentic target | A recipe that writes a jagt task packet for an agent. It does no work itself, other than logged steps that give the agent its inputs, such as `test-parent`. |
| Fresh agent | An agent that a harness starts for one task, for example a subagent. |
| Record | The saved result of an agentic target, with its input tree and its output tree. |
| Harness | A program that runs an agent, for example Claude Code or Codex. |
| Plugin | A small Python script for one harness. It knows where that harness keeps its sessions and transcripts. |
| Adapter | The parts that join one harness to the gates: its hooks in agent_gest_git_skills, and its plugin in the repository of `jlog`. |
| Agent hook | A hook of a harness that runs before or after a tool call. |
| smalldocs | The program that builds the docs websites of the stack. |
| Docments | The comments beside the arguments of a Python function. smalldocs reads them for the API pages. |
| API pages | The pages of a docs website that smalldocs makes from the code of a package. smalldocs 0.5.5 makes them for Python only. |

## The threat model

The gates stop honest mistakes, for example an agent that forgets the review,
or a commit with an unstaged fix. They do not stop an agent that tries to
cheat. An agent with a shell can edit the log, remove the git hook or write a
commit with `git commit-tree`. The spec makes these acts hard to do by
accident.

## Proposed Solution

The sections below describe each part of the solution, from the tools to the
files that the installer writes.

### Who calls what

The diagram shows each part and the parts that it calls. The gate reads the
log and the records, and it runs no step itself.

```
 person / agent
     │  just check                         just review | test-review | docs …
     ▼                                          ▼
 ┌──── jnterfaces ─────────────────────┐  ┌─ agent_gest_git_skills ───────┐
 │ root Justfile + index: step names,  │  │ target recipes, base tasks    │
 │ no-op steps, set shell → jlog       │  │ from the g* skills            │
 └──────┬──────────────────────────────┘  └──────┬────────────────────────┘
        │ each step line                         ▼
        ▼                                 ┌─ jagt render ────────────────┐
 ┌─ jlog (shell wrapper) ─┐               │ packet = base + language     │
 │ runs line, writes      │               │        + repo text + nonce   │
 │ .agents/log/just.jsonl │               │ packets/<nonce>.json         │
 │ jlog pass at the end   │               └──────┬───────────────────────┘
 └──────┬─────────────────┘                      ▼ (jagt-protocol rules)
        ▼                                 fresh agent → AGENT_RESULT
 ┌─ profile modules ───────────────┐             │
 │ python.just, typescript.just,   │             ▼ SubagentStop hook
 │ rust.just → ruff, ty, pytest,   │      writes the record; the jlog
 │ biome, tsc, smalldocs, cargo …  │      plugin gives the model
 └─────────────────────────────────┘             │
                                                 ▼
 git commit ──► pre-commit hook ──► gate (agent_gest_git_skills)
                                      reads: the pass + the chain of records
                                      checks: commit tree = worktree tree
                                      never runs a step itself
```

Each profile provides one module, for example `python.just`, `typescript.just`
or `rust.just`, and one language layer of the packet text.

### The tools

A machine needs these programs. The installer checks each one before it writes
anything. When one is missing, it stops and prints the install line.

| Program | Use | Install |
|---|---|---|
| `git` | Everything | The system package manager. |
| `just` | All recipes | `cargo install just` or the system package manager. |
| `uv` | Python, the installer, smalldocs, nossaifd, the plugins | https://docs.astral.sh/uv/ |
| `jlog` | The run log, as the shell of each recipe | `git clone https://github.com/rahuldave/jlog`, then `just install` in the clone. |
| `jagt` | Agentic targets. Version 0.3.0 or later, for the nonce. | `cargo install --git https://github.com/rahuldave/jagt` |
| `gest` | The task tracker, from the fork of rahuldave | `git clone https://github.com/rahuldave/gest`, then `cargo install --path gest --locked`. On 2026-11-12, `cargo install --git` of the fork failed at the checkout with "the repository is not empty". |
| `gh` | Publishing, GitHub issues | https://cli.github.com/ |
| `jq` | The agent hooks | The system package manager. |
| `rg` | Search, for agents and in the docs | `cargo install ripgrep` or the system package manager. |
| `ast-grep` | The pass that finds code that depends on a change | `cargo install ast-grep` |
| `node` | The TypeScript profile | Through `uv`, as the profile does now. |
| `cargo-llvm-cov` | `coverage-check` in the Rust profile, with the rustup component `llvm-tools-preview` | `cargo install cargo-llvm-cov`, and `rustup component add llvm-tools-preview` |
| `cargo` | The Rust profile, and the builds of `just`, `jlog`, `jagt` and `gest` | https://rustup.rs/ |

- **The other new tools come through the profiles.** `diff-cover` and
  `interrogate` run with `uv run --with`, in any language. eslint and
  eslint-plugin-jsdoc come through npm in the TypeScript profile.
- **`jlog` is required.** Every recipe that does not start with a shebang line
  runs through `jlog`. Without it, such a recipe fails with "could not find the
  shell `jlog`". So `jlog` must be on `PATH` before the first `just install`.
  The installer recipes start with a shebang line, so they run without `jlog`.
- **The stack guide of jnterfaces** lists these programs in its section "What a
  machine needs".

### The steps

Every repository has the same steps, for any language:

```text
just check     fmt-check lint typecheck test coverage-check integration docstring-check docs-check prose-check diff-check
```

- **jnterfaces names the steps.** It holds the list and the meaning of each
  step. The installer writes a no-op step for each name that no installed
  profile and no installed role file defines:

  ```just
  typecheck:
    jlog skip typecheck "no type checker in this repository"
  ```

- **The profiles and roles fill in the steps.** jnprofile-python,
  jnprofile-typescript and jnprofile-rust replace the no-op steps with real
  commands. Most of the commands of a language come from the profile. A role
  file can fill a step too, as nossaifd fills `prose-check`. A repository can
  replace a step of a profile, or a no-op step, with a recipe of the same name
  in its own Justfile.
- **How the installer knows.** It reads recipe names with `just --dump`. The
  root Justfile imports the index, so a dump of the root would also hold the
  old index. So the installer reads the names in this order:
  1. It keeps a copy of the old index. Then it writes the index in its form
     with the modules only. That form has the `mod` lines, with no role
     file, no combined recipe and no no-op step.
  2. It dumps the root Justfile. Those names are the names of the repository.
     The recipes of a module have the name of the module in front, so they
     never meet a step name. If this dump fails, the installer stops with
     the error of `just`. It never goes on as if the repository had no
     recipe.
  3. It dumps each role file alone, and each module alone, as now.
  4. It writes the whole index. It leaves out each combined recipe and each
     no-op step whose name the repository defines. It writes a no-op step only
     for a step name that no role file and no combined recipe has.
  5. When it stops before the end of step 4, it puts the old index back. So
     `just check` keeps the steps that it had.
- **A role step and a repository recipe of one name.** The index imports the
  role file, so both define the name. Then `just` would stop with "Recipe
  redefined". The installer stops first, and it names the recipe and the
  role.
- **Without this rule,** `just` stops with "Recipe redefined". With
  `set allow-duplicate-recipes`, the recipe nearer the root wins. So the
  no-op step of the index would beat the role file that the index imports.
- **A skip counts only for a step that no profile and no role provides.** If
  an installed profile or role provides a step, a skip of that step is a
  failure. So a broken index
  of recipes cannot pass by skipping everything.
- **agent_gest_git_skills tests that the steps exist.** The gate reads
  `just --summary`, which runs no backticks. If a step or a required target is
  missing, the gate stops the commit and says "run `just install`". It holds no
  command of a language.
- **Steps only check.** A step never changes a tracked file, or a file that
  git does not ignore. `fmt-check` checks the format, and `fmt` stays outside
  `just check`. Caches and reports, such as `target/`, `.coverage` and
  `lcov.info`, go to ignored paths. Each profile adds those paths to
  `.gitignore` through the shared-file writer.
- **`coverage-check`** fails when a changed line of code does not run in the
  tests.
  - **The report.** `test` and `integration` write their coverage as LCOV or
    Cobertura files in ignored paths. Python uses `pytest-cov`, TypeScript uses
    `c8` and Rust uses `cargo llvm-cov`.
  - **The check.** The step runs `diff-cover` on the reports of both against
    the parent commit, with `--fail-under 100`. A line that only `integration`
    runs counts when `integration` is in `just check`. When the setup answer
    puts `integration` only in `just verify`, such a line needs a pragma or an
    exclude, or the person moves `integration` back into `just check`.
  - **No old report.** The index of jnterfaces calls `just` once for each
    language and step, so a dependency of one module recipe cannot keep the
    tests from running twice. A run ID does.
    - **Where the ID comes from.** The root Justfile has the line
      `export JLOG_RUN := env("JLOG_RUN", uuid())`. The first `just` call
      makes the ID, and each `just` call inside it inherits it. A module gets
      the ID of the root. A module must not have the line, because `env()`
      reads the process environment, so the module would make a second ID.
    - **The ID is bound to a tree.** A person can set `JLOG_RUN` by hand. So
      `jlog` writes the worktree tree with the first line of a run. `jlog pass`
      and `coverage-check` reject a run whose first tree is not the current
      worktree tree. An old run of the same tree is a valid run.
    - **Who uses it.** `jlog` writes `JLOG_RUN` as the run ID of each line,
      so the steps of one `just check` share one run, even in inner `just`
      calls. `jlog pass` reads the lines of that run.
      `test` and `integration` write it into their reports. `coverage-check`
      reads a report only when its run ID matches. Otherwise it runs the tests
      itself.
  - **Lines left out.** In Python and TypeScript, a line can be left out with
    the pragma of its tool, `# pragma: no cover` or `/* c8 ignore next */`.
    Stable Rust has no pragma for a line, so the Rust profile reads an exclude
    list of files, `.agents/coverage-exclude.txt`, instead. The `test-review`
    target must accept each new pragma and each new entry in the list.
  - **Generated code.** The paths in `.agents/generated.txt` count for neither
    `coverage-check` nor `docstring-check`. Each profile passes them to its
    tools as excludes.
  - **The lists come from the parent.** The steps read `generated.txt` and
    `coverage-exclude.txt` with `git show HEAD:<path>`, so a commit cannot
    exempt its own code. With no parent, or when the parent has no such file,
    `git show` fails and the list is empty. `test-review` judges each new
    entry.
  - **No tests.** When code changed and there is no report, the step fails and
    says "write tests". When no profile provides `test`, the step is a skip.
  - **The first commit.** With no parent, `diff-cover` cannot run. The step
    runs the report tool of the profile over all code with a limit of 100%,
    for example `coverage report --fail-under=100`, `c8 check-coverage --lines
    100` or `cargo llvm-cov --fail-under-lines 100`.
- **`docstring-check`** fails when a class, function or method has no doc,
  and in Python and Rust also a module. It covers private items too. Only the
  public items go on the API pages.
  - **Python:** `interrogate` with `--fail-under 100`. The docments of public
    functions are checked once, by `smalldocs api check` in `docs-check`.
  - **TypeScript:** eslint with only the rule `jsdoc/require-jsdoc` of
    eslint-plugin-jsdoc, set for all classes, methods, functions and arrow
    functions, exported or not. Biome has no rule for a missing JSDoc
    comment, so the profile adds eslint for this one step.
  - **Rust:** `cargo clippy` with `-W missing_docs` and
    `-W clippy::missing_docs_in_private_items`, with `--cap-lints warn`. The
    step reads the JSON messages of clippy, and fails on each item with no doc
    outside `generated.txt`. It does not use `-D`, for two reasons. `-D` fails
    on a generated file too. It also stops clippy before it checks the
    binaries that use a failing library.
  - **A suppression in the code,** such as `#[allow(missing_docs)]` in Rust,
    beats the command line. The docs lens of `review` gives a finding for each
    new one that has no reason.
  - **Its output** lists each item with no doc, with its file and line. The
    author agent writes the docs from this list. No target writes them.
- **`diff-check`** runs `git diff --cached --check HEAD`, so it checks the
  changes of the commit for whitespace errors.
- **A lint finds steps that the run log cannot see.** It finds these:
  - A shebang line or the `[script]` attribute. Such a recipe does not run
    through `jlog`. The test and typecheck recipes of both profiles have
    shebang lines now, so the profiles change.
  - A line with a `-` prefix, which ignores a failure.
  - `[no-cd]`, or a `[working-directory]` attribute on a recipe. Each changes
    the folder in which `jlog` looks for the log folder. The setting
    `set working-directory` that the installer writes into a module, to the top
    of the project, is allowed.
- **`prose-check`** checks the changed pages with the checker of nossaifd.
  - **The pages.** A page is a file that `is_page` of nossaifd's
    `prose_gate.py` accepts, so `prose-check` and the turn gate use one rule.
    It takes `.md` and `.qmd` files, and it skips files such as `AGENTS.md`,
    `CHANGELOG.md` and the folder `.agents/`.
  - **The changed pages on a machine.** `prose_gate.py check-changed` finds
    them: the pages that `git diff --no-renames --diff-filter=AMT HEAD`
    names, and the untracked pages. `T` is a changed type, such as a link
    that became a file. With no commit yet, it compares with the empty tree,
    so each page of the index counts.
  - **The changed pages in CI.** A CI checkout has no change against `HEAD`,
    so that list is empty. In CI, `check-changed` checks the pages that
    changed between `BASE` and `HEAD`, and also the pages that changed against
    `HEAD`. In a clean checkout the second set is empty. On a machine where a
    tool sets `CI`, the second set still holds the pages of the next commit.
    The option `--base REF` does the same outside CI, and it wins over `CI`.
  - **CI is on** when the variable `CI` is set to a value other than empty,
    `0` and `false`.
  - **Where `BASE` comes from.** It is always a merge base, so the check never
    takes in the pages of commits that only the other side has.
    - On a pull request, `BASE` is the merge base of
      `origin/$GITHUB_BASE_REF` and `HEAD`.
    - On a push to the default branch, `BASE` is the commit before the push.
      It is the key `before` of the file at `$GITHUB_EVENT_PATH`. So a direct
      push of several commits gets each of them checked, also when a person
      skipped the gate with `--no-verify`. When `before` is all zeros, the
      push made the branch, as the first push of a new repository does. Then
      the step compares with the empty tree, so each page is checked. When
      `before` is not in the history, or is not an ancestor of `HEAD`, `BASE`
      is `HEAD^`.
    - On another push, a merge queue, or another CI system, `BASE` is the
      merge base of `HEAD` and the default branch. So a branch with several
      commits gets each of them checked, also after a force-push. When that
      merge base is `HEAD` itself, as in a build of the default branch,
      `BASE` is `HEAD^`. The default
      branch comes from the key `repository.default_branch` of the file at
      `$GITHUB_EVENT_PATH`, or else from `origin/HEAD`. When neither gives a
      branch, the step exits with 2.
    - On the first push, with no parent, the step compares the empty tree with
      `HEAD`, with a diff of two arguments. A diff with `...` needs a commit
      on each side, so it cannot take the empty tree.
    - The event `pull_request_target` checks out the base branch, so the diff
      would be empty. The step exits with 2 and names the event
      `pull_request`.
  - **Full history in CI.** The CI job checks out with `fetch-depth: 0`. The
    step asks `git rev-parse --is-shallow-repository`. In a shallow clone, it
    exits with 2 and names `fetch-depth: 0`. So a cut-off history never counts
    as a first push.
  - **No changed page.** The step passes. `check` alone exits with 2 when it
    gets no page, so the step never calls it with an empty list.
  - **The checker.** `check-changed` checks the pages as
    `prose_gate.py check PAGE...` does. The step never calls `check.py`
    directly. `check` applies the map of checkers in
    `.agents/nossaifd-checkers.json`, so a talk repository can check its
    slides with another checker. It names the checker in its output. A
    checker that is missing or that fails is a hard problem. Any exit of
    `check-changed` other than 0 fails the step.
  - **One line.** A step has no shebang line. So the logic goes into
    `prose_gate.py`, and the recipe calls it once.
  - **The recipe** is in the role file of nossaifd,
    `.agents/just/roles/nossaifd.just`, with the name `prose-check`. So it
    fills the step in a project with the `nossaifd` role. Without the role,
    the step is a no-op step.
  - **The API pages.** The step runs `smalldocs api module NAME` for each
    changed module into a temporary file, and checks that file.
  - **No writes.** The step writes nothing into the repository. When
    `prose_gate.py` or its checker is missing, the step fails and prints the
    install line.
- **The `integration` answer** of the setup questions decides whether
  `integration` is in the list. The list is in `.agents/stack.json`. `jlog pass`
  and the gate read the list from there.
- **The contract changes.** The rule "Do not add recipes that do nothing"
  becomes "A step with no tool is a no-op step that logs the skip."

### The docs site and the API pages

Today no profile gives a new project a docs site. The recipes `docs-check` and
`docs-publish` exist only in the Justfiles of jnterfaces, the profile
repositories and agent_gest_git_skills, for their own websites.

- **A `docs` tool in jnterfaces, for any language.** It writes the smalldocs
  config and `docs/index.md`. It fills `docs-check` with `smalldocs check docs`.
  It adds `docs-publish` and a CI workflow that runs it. The name
  `docs-publish` matches the recipes that exist now.
- **An `api` tool in jnprofile-python.** It adds the `api` settings to the
  smalldocs config. The key `packages` names the packages of the project. The
  tool adds `smalldocs api check` to `docs-check`. That command exits with 1
  when it finds a gap, as the code of smalldocs 0.5.5 shows. The step runs it
  with `uv run --with smalldocs==0.5.5`, so the package and its dependencies
  can be imported. The profile turns the tool on by default when the project
  has the `docs` tool.
- **No API pages for TypeScript or Rust yet.** smalldocs 0.5.5 reads the API
  with the Python `ast` module and reads the docments with fastcore. Work is
  under way in smalldocs to read the API of Rust with rustdoc and of TypeScript
  with JSDoc. Until a release has it, a TypeScript or Rust project gets the
  `docs` tool only. After that release, jnprofile-typescript adds an `api` tool
  like the one of Python. That tool pins the new release, and it says which
  source files `@api` names. jnprofile-rust adds its `api` tool after the
  release that reads rustdoc.

### Skills and targets

The skills ask for the work, and the steps and targets check it.

- **The skills ask the author agent to write tests and docs.** `gim`, `gte`
  and `gdo` say that each change needs tests and a doc for each item. The
  author agent has the context of the change, so it writes them. No `jagt`
  target writes tests or docstrings.
- **The steps check that they exist.** `test`, `coverage-check` and
  `docstring-check` are deterministic and logged.
- **The agentic targets check that they are good.** `test-review` checks the
  tests, and the docs lens of `review` checks the docstrings.
- **A part of a skill becomes a target only when the gate needs its
  evidence.** The other parts of the skills stay as they are.
- **The doc pages are the exception.** `just docs` writes the pages that a
  change affects, such as the README and the guides. A fresh agent can do that
  work, because it needs the whole change and not the context of one function.

### The skills

The g* skills keep the craft, and lose the commands of each language. Each
check that a skill runs goes through a recipe, so the run log has it.

| Skill | The change |
|---|---|
| `gim` | It writes the code, the tests and the docs. It ends with `just check` and the required targets, and it fixes what their findings say. It runs no checks of its own. |
| `gte` | It says how to write a good test. It runs tests only through `just test`, `just integration` and `just coverage-check`. It holds the base tasks of `test-review` and `visual-check`. |
| `gfm` | It runs `just fmt`, then the check steps. It names no tool such as ruff or biome, because the profiles own the tools. |
| `gdo` | It asks the author for a doc on every item, and it reads the output of `docstring-check`. It holds the base tasks of `docs` and `visualize`. |
| `grv` | It holds the base task of `review`, with the lenses and the docs lens. To run `grv` by hand is to run `just review`. |
| `gcm` | It commits after the pass and the records. It explains a stop of the gate, asks the person before `record-skip`, and uses stacked PRs with plain git. |
| `gpa`, `gor` | They use stacks with plain git, the shared log folder, and records from worktrees. |
| `gsu` | It runs `just install`, with the setup questions and the check of the tools. |
| `gtw`, `gbs`, `gsp`, `gpl`, `gis`, `gpr` | No change. Their work gives no evidence that the gate needs. |

When a repository has no `just check`, each skill tells the agent to run `gsu`
first.

### Agentic targets

An agentic target adds a skill to the work at the moment that the work needs
it. The skill has typed inputs and a fixed form of result, a little like a
module of DSPy without a signature. The arguments of a `just` recipe are the
inputs. A later spec can add signatures, with a type for each argument and
each field of the result.

The targets work with any harness. They depend only on these parts:

- **`jagt render`** writes an `AGENT_TASK v1` packet. It is plain text, so any
  harness can read it.
- **The rules of the `jagt-protocol` skill.** The agent that reads a packet
  gives the task to a fresh agent, and does not do it itself. The fresh agent
  returns an `AGENT_RESULT v1` packet as its last message. The skill is
  optional in jnterfaces now. It becomes required when the gates are
  installed.
- **An adapter for each harness** says how the result becomes a record. The
  section "Records" lists the adapters.

Each packet has these parts:

- **The base task** from the skill. For example, `grv` gives the review lenses.
  A lens is one point of view of the review, for example correctness, tests or
  safety. The file is `references/targets/<target>.md` in the skill.
- **The language layer** from `.agents/targets/<language>/<target>.md`, for
  each language in `.agents/stack.json`. Each profile ships its files, as it
  ships its `just` modules now. For example, the Python file for `docs` can say
  "write docments for each argument". A new language needs a new file, and no
  change to any skill.
- **The repository text** from `.agents/targets/<target>.md`, if the file
  exists. For example, `.agents/targets/review.md` can say "check each SQL
  migration for a rollback".
- **The inputs:** the diff, the input tree and the arguments of the recipe.
- **The required outputs:** the fields that the result must have, for example
  `findings` and `status`.
- **A nonce:** a random value of 32 lowercase hex digits, whose first digit is
  a letter. It is the one random part of a packet. The rest of the packet text
  is the same for the same inputs. `jagt render` saves the version of the file
  form, the nonce, the target, the input tree, the path of the worktree and the
  hash of the packet in `packets/<nonce>.json` in the shared log folder.
  - **In the packet and the result,** the nonce is a top-level field,
    `nonce:`. The fresh agent copies it from the packet into its
    `AGENT_RESULT v1`.
  - **The check.** Before the hook or `just record` writes a record, it runs
    `jagt result lint --expect-target <target> --expect-nonce <nonce>`. A
    result with another nonce, with none, or with two `nonce` fields gives no
    record.
  - **Without a record.** `jagt render --no-save` gives the text only, with no
    nonce and no file, for demos and labs.

The first agentic targets:

| Target | What the fresh agent does | Its result |
|---|---|---|
| `just review` | An adversarial review of the changes, on the strongest model. The docs lens checks that each new or changed doc says what the item is for, that it matches the code, and that it is not a stub. | Findings, each one fixed with a test or with a reason not to fix it. |
| `just test-review` | Checks that each new behavior has a test, that each new test checks a result, and that each new pragma or exclude has a reason. A new test that passed on the parent commit is a finding, unless the change is a refactor. | Findings, each one fixed with a test or with a reason not to fix it. |
| `just docs [area]` | Finds the docs that the change affects, and writes or changes them. The repository text says which docs the repository has, for example user docs, developer docs, API docs or a change log. | The changed docs, and the docs it checked and left alone. |
| `just prose [path]` | Applies the nossaifd guide to the changed pages and docstrings, beyond `check.py`: the plain-writing pass and the pass that removes the habits of model writing. | The changed pages, and the lint output after the change. |
| `just visual-check [url-or-flow]` | Runs the app, goes through the flow in a browser and takes screenshots. | The screenshots, shown to the person, and a pass or fail for each step of the flow. |
| `just visualize [topic]` | Draws a diagram of a part of the code, for a doc or for the person. | The diagram file and the doc that shows it. |

Before it writes its packet, the `test-review` recipe runs a logged line,
`test-parent`:

- It makes a worktree of the parent commit in a temporary folder outside the
  repository, with `git worktree add --detach`.
- It copies each added or changed test file in, runs the `test-paths` recipe
  of the profile on them, and removes the worktree.
- **Test files.** Each profile names its test files with the globs of the key
  `tests` of `profile.json`. `test-parent` copies only those files, so no
  new code reaches the parent.
- A Rust unit test lives in the file of its code. Copying that file copies the
  new code too, so a pass proves nothing. So the key `tests` of the Rust
  profile names `tests/**` only, and `test-review` judges the unit tests from
  the diff alone.
- **Two limits of the Rust profile.**
  - The tests of a workspace member, such as `crates/x/tests/a.rs`, do not
    match `tests/**`. The glob `**/tests/**` would also take
    `src/x/tests/mod.rs`, which can bring new code into the parent. So
    `test-review` judges the tests of a member from the diff.
  - A build script of a dependency can fail for an outside reason, such as a
    missing system library. cargo prints the same lines as for a test that
    does not build, so `test-paths` exits with 1, not 2.
- **The exit codes of `test-paths`.** Each profile gives the same four:
  - 0: the tests ran and passed.
  - 1: a test failed, or a test did not build. A new test of new code often
    does not build on the parent, and that is a failure of the test.
  - 5: no test ran, as pytest exits when it collects no test. An example is
    a file whose tests are all skipped. `test-paths` with no path exits with
    5 too, and it never runs all the tests.
  - Any other code: the runner itself failed, for example with a usage error
    or a crash.
- **Each profile counts the tests.** It reads the count from the output of
  the runner, such as the summary line of pytest or the lines "running N
  tests" of cargo. A count of 0 gives 5, even when the runner exits with 0. A
  runner that exits with 5 for another reason, such as a fatal error of Node,
  gets 2. vitest exits with 1 when a test fails, and also when it finds no
  test file. So the profile reads its output to tell the two apart.
- **No test file.** When no changed file matches `tests`, as in a change
  with Rust unit tests only, `test-parent` does not call `test-paths`. It
  records "no test ran on the parent".
- **How `test-parent` reads them.** 0 is a pass on the parent. 1 is the
  expected failure. 5 is "no test ran on the parent", and `test-review`
  judges those tests from the diff. Any other code is "the runner failed",
  which is neither a pass nor a failure.
- It writes the result, with the output of the tests, to
  `test-parent/<run>.json` in the log folder. The result names the case. It
  exits with 0 in each case above. It exits with 1 only when `test-parent`
  itself fails. Examples are a worktree that git cannot make, a copy that
  fails, and a log file that it cannot write.
- The packet holds the result. So the run is logged, and the agent only judges
  it.
- On the first commit, `test-parent` is a skip.

The base task of `test-review` is in `gte`, and the base task of `review` is in
`grv`.

Two recipes have the name `prose` now, and both change:

- **The role file of nossaifd** has a recipe `prose`. It becomes
  `prose-check`, and it fills the step in each project with the `nossaifd`
  role.
- **jnterfaces itself** has a recipe `prose checker` in its own Justfile. It
  becomes `prose-check`. In jnterfaces it replaces the step, as the recipe of
  a repository may. When jnterfaces takes the gates for itself, the recipe
  must run with no argument, as each step does.

So `prose` is free for the agentic target.

Other targets to consider later:

- **`just security-review`:** looks for secrets, injection and unsafe input.
- **`just impact [symbol]`:** finds the code that depends on a changed symbol,
  with `ast-grep`.
- **`just pr-text`:** writes the PR description from the commits and records.
- **`just ci-triage [run]`:** reads a failed CI run and finds the cause.

### Setup questions

Some choices of a repository belong to the person, not to the stack. Today the
installer asks yes-or-no questions at a terminal, and only about new roles.
With no terminal and no saved choices, it stops. The spec makes these changes:

- **At a terminal,** the installer asks the open questions itself. A question
  can have more than two answers.
- **With no terminal, under an agent,** the installer writes a packet with the
  open questions, and stops. The packet is a `just setup-questions` packet.
  The agent that ran the installer asks the person, with the question tool of
  its harness. It does not give this packet to a fresh agent, because a fresh
  agent cannot ask the person. Then it runs `just install --answer <key>=<value>`
  for each answer.
- **In CI,** when `CI` is set, the installer takes the defaults and asks
  nothing.
- **A question with an answer** in `.agents/stack.json` is not asked again. A
  later version of the stack can add questions, and then only the new ones are
  asked.

The first questions:

| Key | Question | Default |
|---|---|---|
| `issues` | Which Gest tasks become GitHub issues: every top-level task, only development tasks, or none? | Every top-level task |
| `docs-publish` | Publish the docs site of a public repository after a merge to `main`? | Yes |
| `integration` | Run the integration tests in `just check`, or only in `just verify` before a PR? | In `just check` |
| `tasker` | One branch in the main checkout, or a worktree for each task? The answer sets the variant of the tasker role, `git` or `gitwt`. | `git` |
| `review-model` | Which model does the adversarial review? | The strongest model of the harness |

The required targets are not a question. `.agents/targets/required.txt` is the
only place for them.

### Records

- **A record has two trees.** The input tree is the worktree tree when the
  packet was made. The output tree is the worktree tree when the fresh agent
  stopped, after its changes. A target that changes no file has the same tree
  twice.
- **The chain.** `docs` and `prose` change files, so the gate accepts a chain:

  ```text
  docs         T0 -> T1
  prose        T1 -> T2
  test-review  T2 -> T2
  review       T2 -> T2
  check        T2
  ```

  Each record must start at the output tree of the record before it. The last
  tree must be the commit tree. A `docs` record comes before a `prose` record,
  because `prose` checks the text that `docs` wrote. `test-review` and `review`
  come after the last record that changes files. When a review leads to fixes, the fixes make a
  new tree, and the review runs again on it. `test-review` and `review` change
  no files, so they can run in either order on the same tree.
- **What a record must hold.** A record counts only if its status is
  `success`, and each finding is fixed with a test or has a reason not to fix it.
- **The turn gate of nossaifd stays, with a different job.** nossaifd has its
  own hooks, `UserPromptSubmit` and `Stop`, in Claude Code and Codex. At the end
  of a turn, the `Stop` hook blocks once when a page that the turn changed has
  a hard problem or no recorded pass.
  - **The jobs.** The turn gate asks early, inside a turn, at little cost. The
    commit gate decides. Only the `prose` record and the `prose-check` step let
    a commit through.
  - **One store of page passes.** nossaifd records the pass of a page with
    `prose_gate.py record`, in `nossaifd/` under `git rev-parse
    --git-common-dir`. Every worktree shares it. The store stays there, with or
    without the gates, so it needs no migration.
  - **The `prose` target records each page.** The fresh agent of `just prose`
    runs `prose_gate.py record` for each page that it passed. So a page that
    `just prose` passed does not block a later turn.
  - **A page pass is not a `prose` record.** The gate needs the `prose` record
    of the tree, from the fresh agent.
  - **When the gates are installed,** `.agents/stack.json` lists the tasker
    role. Then the message of the `Stop` block says "run `just prose`". The
    steps by hand alone give a page pass, but no `prose` record.
- **The records are in the shared log folder,** in `records/`. A fresh agent can
  work in another worktree, for example in the parallel work of the `gor`
  skill. The packet holds the path of its worktree, so the hook computes the
  tree in the right checkout.
- **The gate reads only records.** It does not know which harness made them.
- **Who writes a record** depends on the adapter of the harness:

  | Harness | How the result becomes a record |
  |---|---|
  | Claude Code | The `SubagentStop` hook gets the last message of the fresh agent and the path of its transcript. It finds the nonce in the message. The packet file gives the target, the input tree and the worktree. The plugin reads the model from the transcript. |
  | Codex | The same as Claude Code. Codex 0.163 has the hooks `SubagentStart` and `SubagentStop`, with `agent_transcript_path` and `last_assistant_message`. Codex runs the hooks of a project only after the person trusts them. |
  | An older Codex, or any other harness | The agent that ran the target runs `just record <target> <file>`, and the record is marked `"source": "agent"`. |

  A harness with a hook that writes records stops `just record`, so its agents
  cannot write a record by hand.
- **The check of a `just record`** in Codex reads the transcript of the fresh
  agent, a JSONL file:
  - Its `session_meta` line names the parent thread in `parent_thread_id`. The
    parent must be the thread that ran `just record`, from `CODEX_THREAD_ID`.
  - One fresh agent can have several turns. The nonce must be in the
    `last_agent_message` of one of its `task_complete` lines.
  - The model comes from the turn context of the transcript.
  - The check reads no SQLite file. A reader of a database in WAL mode writes
    to its `-shm` file, so a read is not free of writes. A read of
    `~/.codex/state_5.sqlite` on 2026-11-12 changed the time of
    `state_5.sqlite-shm`.
- **A skip with a reason.** `just record-skip <target> <reason>` lets one tree
  through without that record. The agent hooks ask the person before it runs.

### The run log

just has no log of its own. Its options `--timestamp`, `--verbose` and
`--explain` print to the terminal, and its changelog shows that its internal
logging was removed. So each Justfile sets `jlog` as its shell:

```just
set shell := ["jlog", "sh", "-cu"]
```

`jlog` takes the real shell as its first argument, here `sh -cu`. It runs each
line with that shell and the positional arguments of the recipe. Then it adds
one JSON line to the run log:

```json
{"run": "48213-1731405600", "argv": ["just", "check"],
 "line": "uv run ruff check .", "exit": 0,
 "start": "2026-11-12T10:00:00Z", "end": "2026-11-12T10:00:04Z"}
```

- **The run ID.** The field `run` is `JLOG_RUN` when it is set. Without it,
  `run` is the process ID of the parent `just` and its start time, as in the
  example. The section "The steps" says where `JLOG_RUN` comes from.
- **Where `set shell` goes.** The installer writes the profiles as modules of
  just. A module has its own settings, so the installer writes `set shell` into
  each module file that it makes, and into `.agents/install.just`. It also
  writes it into the index file that the root Justfile imports. A setting in an
  imported file applies to the recipes of the root Justfile, as a test on
  2026-11-12 showed.
- **A repository that sets `shell` already.** just stops with "Setting `shell`
  is redefined" when the root Justfile and an imported file both set it. So the
  installer looks for `set shell` in the root Justfile. When it finds one, it
  does not add its own. It asks the person to wrap the shell, for example
  `["jlog", "bash", "-c"]`.
- **The cost.** Tests on 2026-11-12 on this machine measured the extra time for
  each line:

  | Form of `jlog` | Extra time for each line |
  |---|---|
  | A POSIX shell script | About 45 ms |
  | A Python script through `uv` | About 100 ms |
  | A small compiled program | About 1 to 2 ms, by estimate |

  So `jlog` is a small compiled program, in a repository of its own. jagt
  stays a tool for agent packets only.
- **No process for each line, other than the shell.** `jlog` finds the log
  folder by going up from the current folder to the folder that holds
  `.agents/`, with no call to `git`. It computes no tree on each line.
- **`jlog` has no code for a harness.** It reads only the environment and the
  run log. Each harness has a plugin, and `jlog` calls the plugin once for each session.
- **The run** is the process ID of `just` and its start time. It joins the
  lines of one call.
- **The argv** is the `just` command as a list. `jlog` reads it from
  `/proc/<pid>/cmdline` on Linux and with `sysctl` on macOS, which keeps the
  quoting.
- **A skip** comes from a `jlog skip <step> <reason>` line, not from the output
  of a tool. `jlog` does not read the output, so tools keep their terminal and
  colors.
- **Backticks** in a Justfile also run through `jlog`. It tags them as
  `"kind": "backtick"`, and the gates ignore them.
- **The log folder has its own `.gitignore`.** On its first write, `jlog`
  makes `.agents/log/.gitignore` with the one line `*`. A test on 2026-11-12 showed
  that `git add -A`, `git stash -u` and `git clean -fd` then leave the folder
  alone. Without the file, `git stash -u` deleted the folder. jnterfaces also
  adds `.agents/log/` to `.gitignore`, to `.worktreedisposable` and to its list
  of reserved folders. So a worktree with only a log folder can still be
  pruned.
- **Secrets in lines.** A line of a recipe can hold a secret, for example a
  value from a `.env` file or from an argument. `jlog` removes such values
  before it logs `line` and `argv`. It finds each variable that is not on the
  safe list and has a value of 8 characters or more. It replaces each such
  value with `<redacted>`.
- **A request to just.** A `--log-file` option in just itself would remove the
  need for `jlog`. Such a change is a request to the authors of just, outside
  this spec.

### Sessions and the environment

`jlog` has commands of its own:

| Command | What it logs |
|---|---|
| `jlog <shell> <flags> <line>` | One line of a recipe. `just` calls this form. |
| `jlog session` | The harness, the session ID, the path of the transcript and the model. |
| `jlog env` | The environment. |
| `jlog tools` | The version of each program in the tools table. |
| `jlog skip <step> <reason>` | A no-op step. |
| `jlog pass` | The pass of `just check`. |

- **Once for each session.** The first line in a new session also runs
  `session`, `env` and `tools`. `jlog` marks a session as seen with a file
  `.agents/log/sessions/<id>`, so it reads no log to find out.
- **`jlog tools` has a short timeout.** The timeout is a few seconds. It
  starts no download, and its failure never fails the line.
- **The gate is a plain script, not a recipe.** So nothing runs on its own
  inside the git hook.

**Which session.** Each harness shows its session in a different way:

| Harness | How `jlog` finds the session | Source |
|---|---|---|
| Codex | Codex puts `CODEX_THREAD_ID` into each shell command that it runs. | `codex-rs/protocol/src/shell_environment.rs` in openai/codex |
| Claude Code | `CLAUDE_CODE_SESSION_ID` is set in the shell commands. In a fresh agent, `CLAUDE_CODE_CHILD_SESSION` is set too, so `jlog` can tell the lines of a fresh agent from the lines of its parent. If the variable is missing, the `SessionStart` hook writes `export JLOG_SESSION=...` to the file in `CLAUDE_ENV_FILE`. | The environment of a session on 2026-11-12, and the Claude Code hooks docs |
| A person at a terminal | The ID of the terminal session, from `getsid(0)`. All `just` calls in one terminal then share one session. | None |

**The plugins.** The repository of `jlog` has a folder `plugins/`, with one
folder for each harness:

```text
plugins/
  claude/   pyproject.toml  uv.lock  session.py
  codex/    pyproject.toml  uv.lock  session.py
```

- **Each plugin is a uv project of its own.** It has its own `pyproject.toml`,
  its own `uv.lock` and its own environment. So it does not depend on the
  Python of the system, or on the lock file of the repository in which `jlog`
  runs.
- **`jlog` runs a plugin** with
  `uv run --project <plugins>/<harness> --frozen python <plugins>/<harness>/session.py`.
  The option `--frozen` uses the lock file as it is, and never changes it.
- **A test on 2026-11-12** ran a plugin this way from the folder of another
  repository:
  - The plugin used its own environment, in its own folder.
  - The current folder stayed the folder of the repository.
  - The repository did not change.
  - After the first run, a call took about 40 ms.
- **Where the plugins are.** `just install` in the repository of `jlog` builds
  `jlog` and copies the plugins to `~/.local/share/jlog/plugins/`. The variable
  `JLOG_PLUGINS` can name another folder.
- **The plugins need no packages now.** They use `json` from the standard
  library of Python. Their own lock files keep later packages away from other
  projects.
- **A plugin reads only JSONL transcripts.** It opens no database of a
  harness, because a read of a database in WAL mode writes to the folder of
  the harness.
- **A new harness** needs only a new folder in `plugins/`, and its hooks in
  agent_gest_git_skills. `jlog` and the gate do not change.

Each plugin reads the environment and prints one JSON object:

```json
{"harness": "codex", "session": "<thread>", "transcript": "<path of the JSONL file>",
 "model": "<model>", "parent": "<parent thread>"}
```

**The environment.** A recipe runs with `sh`, not with the shell of the person.
A test on 2026-11-12 showed what a recipe gets:

- **It gets** the exported variables of the shell that ran `just`, for example
  `PATH`.
- **It does not get** aliases, shell functions, options, or variables that are
  set without `export`. It does not read `.zshrc`.
- **A git hook** gets the environment of the program that ran `git`. A GUI
  program or a CI runner does not read `.zshrc`.

So these rules apply:

- **A recipe never depends on `.zshrc`.** The settings of a repository go in
  the Justfile, with `set export`, or in an ignored `.env` file, with
  `set dotenv-load`.
- **The installer and the gate check that each program is on `PATH`.** A
  missing program stops them with its install line.
- **`jlog env` logs the names of all variables, and the values of a safe list
  only.** The safe list has exact names, not prefixes. The names are `PATH`,
  `SHELL`, `HOME`, `TERM`, `CI`, `CODEX_THREAD_ID`, `CLAUDE_CODE_SESSION_ID`
  and `CLAUDE_CODE_CHILD_SESSION`. For any other variable, it logs the name and
  the word `redacted`. It also logs whether the value changed since the last
  session. It compares keyed hashes. The key stays on the machine, so a reader
  of the log cannot test a guess of the value.
- **`jlog session` logs paths and IDs only.** It never copies a transcript,
  because transcripts hold secrets.

### The worktree tree

The gates compare trees. An agent leaves its changes unstaged, so the trees
come from the worktree, not from the index. `jlog` computes the worktree tree
with a temporary index:

```sh
GIT_INDEX_FILE=<tmp> git read-tree HEAD
GIT_INDEX_FILE=<tmp> git add -A
GIT_INDEX_FILE=<tmp> git write-tree
```

`GIT_INDEX_FILE` names the index file that git uses. With a temporary file, the
real index does not change. Files that git ignores are not in the tree.

At commit time, the commit tree must equal the worktree tree. So all changes
must be staged:

- **All changes staged.** The commit tree equals the worktree tree, and the
  gates go on.
- **Part of the changes staged.** The commit stops. The gate prints the fix.
  Run `git stash --keep-index -u`, then `just check`, then commit, then
  `git stash pop`.

### The pass

The last line of `check` is `jlog pass`:

```just
check: fmt-check lint typecheck test coverage-check integration docstring-check docs-check prose-check diff-check
  jlog pass
```

`jlog` computes the worktree tree at the first line of a run, and again at
`jlog pass`. `jlog pass` writes a pass for the tree only if all of these hold:

- The nearest `just` above it in the process tree has the argv `just check`
  exactly, with no option and no `NAME=VALUE`.
- No variable of this list is set. The list is `JUST_NO_DEPS`, `JUST_SHELL`,
  `JUST_JUSTFILE`, `JUST_WORKING_DIRECTORY`, `JUST_DOTENV_FILENAME` and
  `JUST_DOTENV_PATH`. Other `JUST_` variables, for example `JUST_COLOR`, do not
  matter.
- The log of this run has lines with exit 0 for each step in the list of
  `.agents/stack.json`. For a step that no profile provides, a skip also
  counts.
- The worktree tree at the end equals the worktree tree at the start.
- The worktree has no unstaged change and no untracked file that git does not
  ignore.

### Gates

- **The gate** is a plain script in agent_gest_git_skills. The git pre-commit
  hook runs it, because only that hook sees the real commit. `git commit -a`
  and `git commit <paths>` each make the index after an agent hook runs. The
  gate does these checks:
  1. It checks that the steps and the required targets exist.
  2. It checks that the commit tree equals the worktree tree.
  3. It looks for a pass for the tree. It never runs the steps itself. A commit
     gives the hook a `GIT_INDEX_FILE`, and tests that run git can write into
     it and break the commit. If there is no pass, the gate stops and says
     "run `just check`".
  4. For a commit by an agent, it looks for a chain of records that ends at the
     tree. It knows an agent by the variables of the harnesses, for example
     `CODEX_THREAD_ID` or `CLAUDE_CODE_SESSION_ID`.
  5. It stops the commit and says which target or step to run.
- **The pre-merge-commit hook** runs the same gate for `git merge`.
- **The pre-commit framework.** The Python profile installs the pre-commit
  framework, which owns `.git/hooks/pre-commit`:
  - The gate becomes a `local` hook in `.pre-commit-config.yaml`, for the
    stages `pre-commit` and `pre-merge-commit`. The config sets
    `default_install_hook_types` to both stages, so that `pre-commit install`
    installs both hooks.
  - The config drops the three hooks that change files. They are
    `ruff-format`, `trailing-whitespace` and `end-of-file-fixer`. `fmt-check` and `diff-check`
    cover them.
  - The framework stashes the unstaged changes before its hooks run. So in a
    Python repository, the gate sees partial staging as a tree that does not
    match, not as unstaged changes. The message is the same.
  - The `lint` tool runs `pre-commit uninstall` when it is removed. The spec
    changes this. When `lint` is removed, the installer writes the plain hook
    in place of the framework hook, so the gate stays.
  - A repository without the framework gets a plain `.git/hooks/pre-commit` and
    `.git/hooks/pre-merge-commit`.
- **The required targets** are in `.agents/targets/required.txt`. Each line
  names a target and the paths that make it required:

  ```text
  review       **
  test-review  @code
  docs         @pages  @api
  prose        @pages  @api
  ```

  - **The default.** When the file is missing, the gate uses these lines.
  - **The syntax** is that of git pathspecs with `:(glob)`. So `*` does not
    match `/`, and `**` does. A deleted path counts as a changed path.
  - **`@api`** names the source files of the packages in `packages`. For a
    package `pkg.sub`, it is `src/pkg/sub/**` or `pkg/sub/**`, whichever
    exists, plus the `check` globs of the `api` settings. The `api` tool of
    each profile defines `@api` for its language. Only Python has one now.
  - **`@pages`** names the files that `is_page` of nossaifd accepts. So
    `AGENTS.md` and `CHANGELOG.md` need no `prose` record. Without the
    `nossaifd` role, `@pages` is `**/*.md` and `**/*.qmd`.
  - **`@code`** names the source files of each language in `.agents/stack.json`.
    Each profile gives its globs under the key `code` of `profile.json`, for
    example `**/*.py`, `**/*.ts` or
    `**/*.rs`. The installer copies them into the key `code` of
    `.agents/stack.json`, for each profile. With no profile, `@code` is empty.
  - **Which file counts.** The gate reads `required.txt`, `.agents/stack.json`
    and `.agents/generated.txt` from the parent of the commit, so a commit
    cannot change the lists for itself. On the first commit of a repository,
    the gate uses the default `required.txt` and the `.agents/stack.json` of
    the commit, and `generated.txt` is empty. When the parent has no
    `.agents/generated.txt`, the list is empty too.
  - **Which changes count.** The gate compares the commit tree with the parent
    of the commit.
  - **Rules:**
    - Every commit needs a `review` record.
    - A commit that changes code needs a `test-review` record.
    - A commit with a docs file needs a `docs` record and a `prose` record.
    - A commit that changes a module of the API pages needs the same two
      records. Its docstrings become text on the website.
    - A change to other code needs neither record.
- **The agent hooks** of each harness do not check records. They parse the
  hook input with `jq`, not `sed`, so a quoted message does not hide a flag. In
  Codex, a `PreToolUse` hook that exits with 2 stops the command. The hooks stop
  these commands as a best effort:
  - `--no-verify`, and `-n` with `commit`.
  - `core.hooksPath`, `git commit-tree` and `git update-ref`.
  - `just record`, in a harness with a hook that writes records.
  - A write to a log folder, `.git/hooks`, `required.txt` or the settings of
    the hooks.
- **Other commands that make commits:**

  | Command | Gate |
  |---|---|
  | `git commit` | The pre-commit hook. |
  | `git merge` | The pre-merge-commit hook. |
  | `git rebase`, `git cherry-pick`, `git revert` | Allowed. A lab checks which trees they make. |

- **The cost.** The agent runs `just check` before it commits, and the gate
  only reads the pass. Integration tests stay in `just check` by default, so a
  slow suite makes each commit slow. The setup question `integration` can move
  them to `just verify`, which runs before a PR.

### Stacked PRs with plain git

The spec drops GitButler, so a stack of dependent PRs uses plain git:

- Each branch starts from the branch below it.
- `gh pr create --base <parent branch>` opens the PR of each branch.
- `git rebase --update-refs` moves the branches of a stack together after a
  change to a lower branch. Git 2.38 and later have it.
- A recipe of the tasker role opens the PRs of a stack in order, from the bottom
  branch up.

### Docs publishing

- **The trigger** is the CI workflow of the `docs` tool, on a push to `main`.
  It runs `just docs-publish`.
- **The workflow** has `permissions: contents: write` and sets
  `GH_TOKEN: ${{ github.token }}`, so `gh` and the push to `gh-pages` work.
  The GitHub Pages source needs one setting by a person, once.
- **The visibility check.** `just docs-publish` asks
  `gh repo view --json visibility`. It publishes with smalldocs only on
  `PUBLIC`. On `PRIVATE` and on `INTERNAL`, it logs a skip.
- **Errors.** On a machine of a person, an error of `gh` logs a skip, so a
  failure never publishes. In CI, where `CI=true`, an error of `gh` fails the
  job, so a missing token shows as a failure.

### The files that the installer writes

The installer of jnterfaces already composes shared files. Each owner declares
its `lines` and its `parts`. The installer keeps one block for each owner, and
an uninstall removes only that block. `scripts/formats.json` says how to read
and write each shared file. The spec uses this writer for each file that it
adds to:

| File | Owner | Piece |
|---|---|---|
| `.gitignore` | jnterfaces | The line `.agents/log/`. |
| `.worktreedisposable` | jnterfaces | The line `.agents/log/`. |
| `.gitignore` | Each profile | The paths of its caches and coverage reports. |
| `.agents/generated.txt`, `.agents/coverage-exclude.txt` | jnterfaces writes them empty, once, in a project that it started | The person or the agent adds paths, and creates the file when it is missing. `test-review` judges each one. A project with a Justfile of its own gets neither file, and a missing list counts as empty. |
| `.pre-commit-config.yaml` | The tasker role | A `local` hook that runs the gate. The writer keys the entries of `repos` by `repo`, so all `local` entries share one key. `formats.json` changes to key a `local` entry by the `id` of its hook. |
| `.claude/settings.json` | The tasker role | The hooks `SessionStart`, `SubagentStop` and `PreToolUse`. The hooks of GitButler go: `Stop` with `gitbutler-snapshot.sh`, and `gitbutler-vcs-context.sh`. |
| `.codex/hooks.json` | The tasker role | The hooks `SessionStart`, `SubagentStop` and `PreToolUse`. The GitButler hooks and text go. |
| `.claude/settings.json`, `.codex/hooks.json` | The `nossaifd` role | The turn gate of nossaifd, `UserPromptSubmit` and `Stop`, as now. |
| The smalldocs config | The `docs` tool and the `api` tool | The site settings, and the `api` settings. `formats.json` needs a new entry for this file. |

The `nossaifd` role also writes `.github/workflows/nossaifd-prose.yml`, as a
`seed` and as a `starter`. Each is a whole file, not a piece. When the tasker
role is installed, `just check` in CI runs `prose-check`. So the installer
removes that file, whichever entry wrote it, and does not write it again while
the tasker role is installed.

The tasker role writes the CI job, `.github/workflows/check.yml`, as a
`starter` only. It is a whole file, and it is yours from then on. An older
installer takes a `seed` out on removal, so the job has no `seed`. The tasker
role ships it only after jnterfaces writes the `check` recipe:

- **The events.** It runs on each push and each pull request. It does not use
  `pull_request_target`, which would give the code of the pull request the
  secrets of the repository.
- **The history.** The checkout has `fetch-depth: 0`, so `prose-check` can
  find the changed pages.
- **The tools.** It installs `just`, `uv`, and `jlog` at a tagged release. The
  person adds the setup of the tools of a language that the runner lacks.
- **The run.** It runs `just check` on the committed files, and not
  `just install`. An install can change tracked files, and then `jlog pass`
  refuses the run, because it needs a clean worktree.

The run log, the packets and the records are not pieces. The runs write them,
in the log folders.

### Where each part lives

| Part | Repository |
|---|---|
| The step names, the no-op steps, the lint of steps, the `docs` tool, `set shell` in the generated files | jnterfaces, in the `just` skill and the installer |
| The setup questions and `just install --answer` | jnterfaces |
| The packets and the nonce, in `jagt render` | jagt |
| The rules for the nonce in the `jagt-protocol` skill | jnterfaces, which ships the skill |
| The real steps of Python, and the `api` tool | jnprofile-python |
| The real steps of TypeScript, with eslint for `docstring-check` | jnprofile-typescript |
| The real steps of Rust, and later its `api` tool | jnprofile-rust, a new repository |
| The language layer of the packet text, the `@code` globs, and the `tests` globs with the exit codes of `test-paths` | each profile |
| The names `coverage-check` and `docstring-check`, as no-op steps, and, in a project that jnterfaces started, the empty `.agents/generated.txt` and `.agents/coverage-exclude.txt` | jnterfaces |
| The entry `rust` in the `profiles` of `stack.json` | jnterfaces |
| The `test-paths` recipe of each profile | each profile |
| The line `export JLOG_RUN` in the root Justfile, and not in a module | jnterfaces |
| `JLOG_RUN` as the run ID of each line of the run log, and the tree of the first line of a run | jlog |
| The run ID in the coverage reports, and the match in `coverage-check` | each profile |
| The recipe `test-parent` | agent_gest_git_skills |
| The `api` tool of TypeScript, after the smalldocs release that reads JSDoc | jnprofile-typescript |
| The base task of `prose`, `check.py`, `is_page`, and the turn gate with its message when the gates are installed | nossaifd |
| The `prose-check` recipe, in the role file `.agents/just/roles/nossaifd.just`, with its CI mode and the install line when `prose_gate.py` or a checker is missing | nossaifd |
| The removal of `nossaifd-prose.yml` when the tasker role is installed, and the rule that keeps a reinstall from writing it again | jnterfaces, in the installer |
| `jlog`, and the plugins, one folder and one uv project for each harness | jlog |
| The gate, the git hooks, the agent hooks, the agentic targets with their base tasks, `just record` | agent_gest_git_skills |
| The CI job `.github/workflows/check.yml`, a starter of the tasker role that runs `just check` | agent_gest_git_skills |
| The removal of GitButler from the hooks, the skills and the docs | agent_gest_git_skills |
| Stacked PRs with plain git, in the `gcm`, `gpa` and `gor` skills | agent_gest_git_skills |
| The changes to the skills, in the section "The skills" | agent_gest_git_skills |

### Delivery

After the spec is approved:

1. `gsp` saves this spec as a Gest artifact in agent_gest_git_skills.
2. `gpl` makes one top-level Gest task for each repository in the table above.
3. `gpr` makes each top-level task a GitHub issue in its repository. A parent
   issue in agent_gest_git_skills holds the spec and links to the others.

The work on `jlog` starts first, in `~/Projects/jlog`, because every recipe
needs it.

## Scope

### In Scope

- The tools table, and the check of the installer for each program.
- `jlog`: the shell form, the commands `session`, `env`, `tools`, `skip` and
  `pass`, the redaction of secrets, and the plugins for Claude Code and Codex.
- The steps, the no-op steps, the lint of steps, the run log and the pass.
- `set shell` in the files that the installer generates.
- The `docs` tool and the `api` tool, and an entry for the smalldocs config in
  `formats.json`.
- The agentic targets `review`, `test-review`, `docs`, `prose`,
  `visual-check` and `visualize`, with the language layer, the repository text
  and the nonce.
- The steps `coverage-check` and `docstring-check` in each profile.
- jnprofile-rust, with the real steps and no `api` tool.
- The setup questions, `just install --answer`, and the defaults in CI.
- The records, the chain, the shared log folder, the required targets and the
  skip with a reason.
- The gate, the pre-commit and pre-merge-commit hooks, the local hook for the
  pre-commit framework, and the agent hooks of each adapter.
- The removal of GitButler, and stacked PRs with plain git.
- The CI workflow that runs `just docs-publish`.
- Labs for each gate and for each command in the table of commands.

### Out of Scope

- New tools for a language, other than those for `coverage-check` and
  `docstring-check`, and the tools of jnprofile-rust.
- A model inside the git hook. A git hook cannot start an agent.
- A defense against an agent that tries to cheat.
- API pages for TypeScript, until smalldocs has a release that reads JSDoc.
- API pages for Rust, until smalldocs has a release that reads rustdoc.
- The targets in the list "Other targets to consider later".
- Signatures for agentic targets.
- Adapters for harnesses other than Claude Code and Codex.

## Acceptance Criteria

**`jlog` and the log:**

- In a new repository with no language, `just check` passes, and the run log
  shows each step as skipped.
- In a new Python repository and a new TypeScript repository, `just check` runs
  the real steps, and a failed step stops the commit.
- Each line of each step, in the root Justfile and in the modules, is in the
  run log.
- A repository with `set shell := ["bash", "-c"]` keeps working, after the
  person wraps it as `["jlog", "bash", "-c"]`.
- The lint finds a shebang step, a `-` line and a `[no-cd]` step.
- `.agents/log/` stays after `git add -A`, `git stash -u` and `git clean -fd`.
- A worktree with only a log folder can be pruned.
- A backtick line is tagged `"kind": "backtick"`.
- A secret from a `.env` file does not appear in `line` or `argv`.
- `jlog tools` logs the versions, and a missing program does not fail a line.
- The cost of each line over the shell itself is measured and reported.

**The pass:**

- No pass is written for `just --no-deps check`, for `JUST_NO_DEPS=true just
  check`, for `just v=x check`, for `jlog pass` run directly, or with an
  unstaged change.
- A skip of a step that an installed profile provides fails the pass. The lab
  of `jlog` uses a stub profile for it.
- `JUST_COLOR=always just check` can pass.

**The commit tree:**

- `git commit -a` by an agent stops if the records cover only the staged
  files.
- A commit with partial staging stops, and the gate prints the fix with
  `git stash --keep-index -u`.
- The first commit of a new repository works with the default list.
- `git merge` runs the gate through the pre-merge-commit hook.

**Records:**

- An agent commit with no review record for the tree stops.
- The chain docs, prose, test-review, review and check passes, and so does
  the chain with `review` before `test-review`. A chain with `prose` before
  `docs` stops.
- A record with status `failed`, or with a finding that is not fixed, does not
  count.
- A review by a fresh agent in another worktree gives a record that the gate
  finds.
- `just record-skip review "typo"` asks the person, then lets one tree through,
  and the run log keeps the reason.
- The text of `.agents/targets/review.md` appears in the review packet.
- `jagt render` saves `packets/<nonce>.json` with the target, the input tree,
  the path of the worktree and the hash of the packet. A result with another
  nonce, or with none, gives no record.
- The record shows the model of the fresh agent, in Claude Code and in Codex.
- The same review gate works in Claude Code and in Codex.
- `just visual-check` and `just visualize` each write a packet that
  `jagt lint` accepts.

**Sessions and the environment:**

- In Codex, each line in the run log has the thread ID, and `jlog session`
  gives the path of the transcript.
- In Claude Code, each line has the session ID, and the lines of a fresh agent
  are marked as such.
- At a terminal, all `just` calls in one terminal share one session.
- `jlog env` shows any secret as `redacted`.
- No plugin writes in the folders of a harness.
- A recipe that needs a setting from `.zshrc` fails the lab, with a message
  that names `set export` or `.env`.

**Setup:**

- The installer stops with the install line when a program in the tools table
  is missing.
- `just install` run by an agent writes a packet with the open questions.
- After `just install --answer issues=none`, that question is not asked again.
- In CI, the installer takes the defaults and asks nothing.
- No hook, skill or doc of agent_gest_git_skills names GitButler or `but`.
- A stacked PR with plain git and `gh` passes the gates.

**Hooks:**

- The hook that stops a commit says which target or step to run.
- `git commit -m "fix" --no-verify` by an agent stops.
- An empty `required.txt` in the commit does not remove the review.
- A test suite that runs git in temporary repositories does not break the
  commit, because the gate does not run the steps.
- In a Python project, the gate runs as a local hook of the pre-commit
  framework, and removing the `lint` tool keeps the gate.

**The turn gate of nossaifd:**

- A page that `just prose` passed, in any worktree, does not block the end of
  a later turn.
- A page with a recorded pass and no `prose` record still stops a commit that
  needs a `prose` record.
- With the tasker role installed, the `Stop` block says "run `just prose`".
- When the tasker role is installed, `nossaifd-prose.yml` is removed. Without
  it, the file stays as now.
- A reinstall of nossaifd after the tasker role does not bring back
  `nossaifd-prose.yml`.
- With the tasker role, the project gets `.github/workflows/check.yml`. Its
  job checks out with `fetch-depth: 0` and runs `just check`. With the
  `nossaifd` role too, a push of a page with a hard problem fails it. A CI file
  of the person stays as it is, and the file stays after `just uninstall`.
- `prose-check` and the turn gate accept the same pages, a `.qmd` file
  included. A change to `CHANGELOG.md` alone needs no `prose` record.
- The removal of the GitButler `Stop` hook keeps the nossaifd `Stop` hook.

**Tests and docstrings:**

- In each of the three profiles, a changed line that no test runs fails
  `coverage-check`. In Python and TypeScript, a pragma on that line makes it
  pass. In Rust, an entry for its file in the exclude list makes it pass.
- A line that only `integration` runs passes `coverage-check` when
  `integration` is in `just check`.
- A commit that adds its own path to `generated.txt` or
  `coverage-exclude.txt` still fails `coverage-check`. So does a commit that
  creates one of these files with its own path in it.
- In a project with no `.agents/generated.txt` or
  `.agents/coverage-exclude.txt`, `coverage-check`, `docstring-check` and the
  gate act as with empty lists. A missing file fails none of them.
- When code changed and there is no coverage report, `coverage-check` fails
  and says "write tests".
- For a change with Rust unit tests only, `test-parent` does not call
  `test-paths`, and it records "no test ran on the parent", not a pass.
- A runner that crashes on the parent gives "the runner failed" in the result
  of `test-parent`, not a failure of the test.
- A new test in an existing test file that fails on the parent commit makes
  `test-parent` exit with 0, and its result file names the test.
- A commit that removes a language from `.agents/stack.json` still needs a
  `test-review` record for the code of that language.
- No hook, skill or doc of agent_gest_git_skills names ruff, biome, pytest or
  another tool of a language.
- In a repository with no `just check`, each skill of the table in "The
  skills" tells the agent to run `gsu`.
- In `just check`, the tests of each language run once, and the run log
  shows one `JLOG_RUN` for all lines.
- `jlog pass` finds each step of `just check` when the index runs the steps in
  inner `just` calls.
- A recipe of a module shows the `JLOG_RUN` of the root.
- `JLOG_RUN` set by hand to the ID of an old run of another tree gives no pass,
  and `coverage-check` does not read that run's report.
- `coverage-check` does not read a report with another run ID. So
  `just coverage-check` alone runs the tests again.
- In Rust, an item with no doc in a file of `generated.txt` passes
  `docstring-check`, and one outside it fails, with its file and line.
- A path in `.agents/generated.txt` fails neither `coverage-check` nor
  `docstring-check`.
- On the first commit, `coverage-check` runs the report tool of the profile
  over all code with a limit of 100%, and `test-parent` is a skip.
- `just check` in a fresh clone leaves no file that git does not ignore.
- In each of the three profiles, a private function with no doc fails
  `docstring-check`, and the output names its file and line.
- A commit that changes code and has no `test-review` record stops. A commit
  that changes only docs needs no `test-review` record.
- `test-review` gives a finding for a new test that passes on the parent
  commit, and for a new pragma with no reason.
- The `review` packet has the docs lens, and a stub doc such as "Returns the
  result." gives a finding.
- The `docs` packet of a Python project holds the Python language layer.
- A new Rust project gets `just check` with real steps, and no `api` step.

**Docs:**

- A new Python project with the `docs` tool has the `api` tool, and a public
  function with no docments fails `just check`.
- Until the smalldocs release that reads JSDoc, a new TypeScript project with
  the `docs` tool passes `just check`, with no `api` step.
- `prose-check` runs `prose_gate.py check-changed` on the changed pages, the files
  that `is_page` accepts, and writes nothing into the repository. A page that
  `.agents/nossaifd-checkers.json` maps to another checker gets that checker.
  When `prose_gate.py` or its checker is missing, the step fails and prints
  the install line.
- With the `nossaifd` role, the role file fills `prose-check`. `just
  --summary` parses, and `just prose-check` runs the recipe of the role file,
  not a no-op step. Without the role, `prose-check` is a no-op step.
- A change with no page passes `prose-check`, and so does the first commit of
  a repository with no page.
- In CI, a pull request that adds a page with a hard problem fails `just
  check`. So does a push of a branch whose first commit adds that page.
- With `CI=1` on a machine, a page with a hard problem that is not committed
  yet still fails `prose-check`.
- A repository with its own `test` recipe, and no
  `set allow-duplicate-recipes`, still gets the combined recipes and the
  no-op steps of the other names. Two runs of `just install` in a row write
  the same index.
- In a Python project with the `api` tool, `prose-check` also checks the API
  pages of each changed module, through a temporary file.
- In CI, `just docs-publish` pushes to `gh-pages` for a public repository.
- It skips a private repository, and it fails in CI when `gh` has no token.

## Open Questions

- `CLAUDE_CODE_SESSION_ID` is also set in a terminal that Claude Code starts. A
  person who types there counts as an agent. Is that acceptable?
- Can the Codex sandbox write to `.git` in workspace-write mode? If it cannot,
  `git write-tree` cannot write tree objects there, and `test-parent` cannot
  run `git worktree add`. A lab must find out. A
  remedy is to write the objects to a temporary folder, with
  `GIT_ALTERNATE_OBJECT_DIRECTORIES`.
- Can the Codex sandbox write to the shared log folder, when a worktree is
  outside the main checkout?
- Does `CLAUDE_ENV_FILE` reach the shell commands of a fresh agent?
- Should the run log rotate, for example after 10,000 lines?
- Which model counts as the strongest model? The setup question
  `review-model` lets each repository choose.

## References

- jnterfaces `.agents/skills/just/references/command_contract.md`
- jnterfaces `.agents/skills/jagt-protocol/references/protocol_contract.md`
- jnterfaces `scripts/install_stack.py`, `scripts/shared_files.py` and
  `scripts/formats.json`
- jnprofile-python `.agents/just/python/test.just`, with a shebang line, and
  `profile.json`, which installs the pre-commit framework
- agent_gest_git_skills `.agents/skills/grv/SKILL.md`
- agent_gest_git_skills `.claude/hooks/pre-commit-context.sh` and
  `raw-git-write-guard.sh`
- The Claude Code hooks docs, for `SubagentStop`, `SessionStart` and
  `CLAUDE_ENV_FILE`, at https://code.claude.com/docs/en/hooks
- openai/codex `codex-rs/protocol/src/shell_environment.rs`
- The hook names in the Codex binary 0.163.0-alpha, and the format of its
  rollout files, read on 2026-11-12
- smalldocs 0.5.5, `api.py`
- The three adversarial reviews of 2026-11-12, and their tests with git and
  just 1.50
- The just changelog, entry "Remove logging" (#2305)
