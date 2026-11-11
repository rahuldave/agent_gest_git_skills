# GSU language profile labs

These disposable labs check that `gsu` can join setup snippets for several
kinds of project. A setup snippet is a short template file, for example a set
of ignore rules or the recipes of a `Justfile`. A profile is the set of
snippets for one kind of project. The labs are examples, and they are not
reference generators of projects. Use them to test the workflow in a new chat
or in a clean project. Then delete the lab folders.

The repository has a live local end-to-end harness for the labs:

```bash
just language-profile-labs
```

The command makes four disposable repositories, for Python/UV, TypeScript/NPM,
Go and Rust/Cargo. In each repository, it does these steps:

1. It starts Git and a local Gest.
2. It joins the `.gitignore`, `.envrc` and `Justfile` snippets of the profile.
3. It runs the commands for setup and verification.

The command does not make GitHub remotes or pull requests. The labs are setup
profiles for languages, and they are not tutorials for the flow of a pull
request.

Each lab must show these results:

- Git starts in the folder.
- Local Gest starts with `gest init --local`.
- The `.gitignore` has the base rules and the ignore rules of the profile.
- The `Justfile` gives a stable command contract.
- Dependencies and caches stay in the folder, where that applies.
- `just verify` runs the checks for lint, types, build, tests, smoke and diff.

## Python With UV

Profile snippets:

- `templates/gitignore/base.gitignore`
- `templates/gitignore/python-uv.gitignore`
- `templates/env/env.example`
- `templates/env/envrc.local-bin`
- `templates/env/python-uv.envrc`
- `python-uv.just`, from the `just` skill of jnterfaces

Local state:

- `.venv/` holds the dependencies.
- `.local/uv-cache` holds the cache of uv.
- `.envrc` can expose `.local/bin` and `UV_CACHE_DIR`.
- Commit `uv.lock` when uv makes it.

The hello-world verification used these commands:

```bash
git init
git branch -m main
gest init --local
direnv allow .
just setup
direnv exec . just verify
```

The lab copies `python-uv.just` from the `just` skill of jnterfaces as its
`Justfile`. Its recipes are `setup`, `hook`, `fmt`, `lint`, `typecheck`,
`test`, `cov` and `diff-check`. `verify` runs `fmt --check`, `lint`, `test` and
`diff-check`.

`just test` runs `uv run pytest`. This command does not put the project folder
on the import path, so `from hello import greet` fails without help. The lab
adds this setting to its `pyproject.toml`, as the `test` tool of
jnprofile-python does:

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
```

## TypeScript With NPM

Profile snippets:

- `templates/gitignore/base.gitignore`
- `templates/gitignore/typescript-npm.gitignore`
- `templates/env/typescript-npm.envrc`
- `npm-local-cache.just`, from the `just` skill of jnterfaces
- `typescript-npm.just`, from the `just` skill of jnterfaces

Local state:

- `node_modules/` holds the dependencies.
- `.local/npm-cache` holds the cache of npm.
- `.envrc` can expose `.local/bin` and `npm_config_cache`.
- Commit `package-lock.json` when npm makes it.

The hello-world verification used these commands:

```bash
git init
git branch -m main
gest init --local
direnv allow .
just setup
direnv exec . just verify
```

The lab verified this command contract:

```just
export npm_config_cache := ".local/npm-cache"

setup:
  npm install

lint path="src package.json tsconfig.json":
  npm exec -- biome check {{path}}

typecheck:
  npm exec -- tsc --noEmit

build:
  npm exec -- tsc

test target="":
  npm exec -- tsc
  node --test dist/*.test.js {{target}}

smoke:
  npm exec -- tsc
  node dist/index.js

diff-check:
  git diff --check

verify: lint typecheck build test smoke diff-check
```

Lessons:

- Include `@types/node` for TypeScript that runs on Node.
- By default, lint the source and the configuration, and not the generated
  `dist/`.

## Go

Profile snippets:

- `templates/gitignore/base.gitignore`
- `templates/gitignore/go.gitignore`
- `templates/env/go.envrc`
- `go.just`, from the `just` skill of jnterfaces

Local state:

- `.local/go-build` holds `GOCACHE`.
- `.local/go-mod` holds `GOMODCACHE`.
- `.envrc` can expose `.local/bin`, `GOCACHE` and `GOMODCACHE`.
- `go.mod` pins the version of the Go language.
- Commit `go.sum` when Go makes it.

The hello-world verification used these commands:

```bash
git init
git branch -m main
gest init --local
direnv allow .
direnv exec . just verify
```

The lab verified this command contract:

```just
fmt:
  gofmt -w .

lint:
  GOCACHE="$PWD/.local/go-build" GOMODCACHE="$PWD/.local/go-mod" go vet ./...

typecheck:
  GOCACHE="$PWD/.local/go-build" GOMODCACHE="$PWD/.local/go-mod" go test ./... -run '^$'

build:
  GOCACHE="$PWD/.local/go-build" GOMODCACHE="$PWD/.local/go-mod" go build ./...

test target="./...":
  GOCACHE="$PWD/.local/go-build" GOMODCACHE="$PWD/.local/go-mod" go test {{target}}

smoke:
  GOCACHE="$PWD/.local/go-build" GOMODCACHE="$PWD/.local/go-mod" go run .

diff-check:
  git diff --check

verify: fmt lint typecheck build test smoke diff-check
```

Lesson: `GOCACHE` must be an absolute path. In a recipe of `just`,
`$PWD/.local/go-build` gives that path.

## Rust With Cargo

Profile snippets:

- `templates/gitignore/base.gitignore`
- `templates/gitignore/rust-cargo.gitignore`
- `templates/env/rust-cargo.envrc`
- `templates/rust/rust-toolchain.toml`
- `rust-cargo.just`, from the `just` skill of jnterfaces

Local state:

- `target/` holds the build artifacts of Cargo.
- `rust-toolchain.toml` pins the channel of the Rust toolchain.
- Commit `Cargo.lock` for apps and binaries. For a library, ask before you
  ignore it.

The hello-world verification used these commands:

```bash
git init
git branch -m main
gest init --local
direnv allow .
direnv exec . just verify
```

The lab verified this command contract:

```just
fmt:
  cargo fmt --all

lint:
  cargo clippy --all-targets --all-features -- -D warnings

typecheck:
  cargo check --all-targets --all-features

build:
  cargo build --all-targets --all-features

test target="":
  cargo test --all-features {{target}}

smoke:
  cargo run --quiet

diff-check:
  git diff --check

verify: fmt lint typecheck build test smoke diff-check
```

Lesson: the toolchain is outside the repository, but the repository can pin it
with `rust-toolchain.toml`. The build artifacts stay local, in `target/`.

## Add a profile for a new kind of project

When a new kind of project appears, `gsu` does these steps:

1. It writes candidate snippets.
2. It asks the user about each real choice of policy.
3. It runs a disposable lab or a focused check of the setup.
4. It moves the stable snippets into `templates/`.

These profiles are good candidates for the next labs:

- Python machine learning with `uv` or `pixi`.
- Python notebooks.
- A browser UI in TypeScript, with spot checks in a browser.
- Separate profiles for a Rust library and a Rust binary.
- A Go service with generated OpenAPI or protobuf artifacts.
