# Just Command Contract

A project command contract is the stable executable interface agents should use
instead of guessing language-specific commands. In repositories that use Just,
the contract is split across:

- `Justfile`: the executable target definitions
- `AGENTS.md`: the human-readable mapping from workflow concepts to targets

Keep both in sync. When a new workflow concept becomes standard for a project,
add or update the Just target and document the mapping in `AGENTS.md`.

## Standard Concepts

Use target names that are stable across projects when they apply:

```text
Format: just fmt [path]
Lint: just lint [path]
Typecheck: just typecheck
Static/compile check: just static
Build: just build
Focused tests: just test [target]
Regression tests: just regression [target]
Integration tests: just integration [target-or-flow]
Smoke checks: just smoke
Run app: just dev [port]
Browser spot check: just browser [url-or-flow]
Diff hygiene: just diff-check
Full local verification: just verify
```

Not every project needs every target. Prefer a smaller honest contract over a
large contract with placeholders.

## Arguments

Just target arguments are positional at the command line:

```just
lint path=".":
  uv run ruff check {{path}}

test target="tests":
  uv run pytest {{target}}

dev port="8001":
  uv run uvicorn app.main:app --host 127.0.0.1 --port {{port}}
```

Agents then run:

```bash
just lint app/models.py
just test tests/test_models.py
just dev 8001
```

Document the positional argument shape in `AGENTS.md`.

## Recipe Composition

Just is a command runner, not a file-freshness build system. For aggregate
recipes, prefer native Just dependencies over recursively calling `just` inside
a recipe body:

```just
diff-check:
  git diff --check

verify: lint typecheck static test smoke diff-check
```

For Just, dependency order is meaningful: dependencies run before the recipe
that depends on them, and in the listed order. Dependencies with the same
arguments run once per `just` invocation.

Use recursive `just` calls only when a recipe genuinely needs to invoke another
recipe in the middle of its own shell body.

References:

- Just dependencies: https://just.systems/man/en/dependencies.html
- Just skill reference: https://raw.githubusercontent.com/casey/just/refs/heads/master/skills/just/SKILL.md

## Incremental Builds And Pipelines

Use `cx` when a project has explicit file-producing build or pipeline stages
inside linewise Just recipes. `cx` is not for tests. It adds command-line
incrementality to a single stage while `just` still owns recipe ordering.

Good fits include ML/AI pipelines, conversion pipelines, generated artifacts,
and hand-written C/C++ compile/link flows. Poor fits include tests, lint,
format, typecheck, browser checks, ordinary `cargo build`, `go build`, `tsc`,
or commands without durable file outputs.

Document any `cx`-backed targets in `AGENTS.md`, for example:

```text
Build pipeline: just pipeline
Incremental build: just build
cx lint: cx lint
```

Keep `.cx/state.json`, `.cx/graph.json`, and `.cx/tmp/` out of version control.
Do not ignore `.cx/config.toml` unless the project explicitly decides it is
local-only.

For examples and verification expectations, see
[`cx_incremental_pipelines.md`](cx_incremental_pipelines.md). The reusable
`just cx-examples-lab` target verifies one staged artifact pipeline and one C
incremental build.

## Browser Checks

Browser checks need both sides of the contract:

- A run-app target, commonly `just dev [port]`
- A browser target, commonly `just browser [url-or-flow]`

The browser target may be a thin wrapper around the project's browser tool:

```just
browser url:
  agent-browser open {{url}}
```

Browser checks should either start from the documented run-app target or
explicitly confirm that the expected server is already running. Do not put
browser checks in `verify` by default unless the project has made server
lifecycle and browser dependencies reliable enough for routine verification.

Repeated browser flows should become durable integration scripts or tests, with
`just integration [target-or-flow]` as the stable entrypoint when appropriate.
