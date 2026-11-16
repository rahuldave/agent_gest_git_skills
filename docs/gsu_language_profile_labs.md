# GSU language profile labs

These disposable labs set up one project for each of several languages, and
check it with `just verify`. Python, TypeScript and Rust use a profile of
jnterfaces. A profile is the set of tools, configs and recipes for one
language. Go has no profile, so its lab joins the setup snippets of `gsu`.

A setup snippet is a short template file, for example a set of ignore rules or
the recipes of a `Justfile`. The labs are examples, and they are not
reference generators of projects. Use them to test the workflow in a new chat
or in a clean project. Then delete the lab folders.

The repository has a live local end-to-end harness for the labs:

```bash
just language-profile-labs
```

The command makes four disposable repositories, for Python, TypeScript, Go and
Rust. Python, TypeScript and Rust have a profile of jnterfaces, and Go has
none. So the labs start in two ways:

- **A lab with a profile** runs `install_stack.py --profile NAME --defaults` of
  jnterfaces, with each tool that the profile leaves off by default. The
  profile writes the manifest, the tool configs and the `Justfile`, as in a
  real project. The lab writes only the code and a test, then runs `just fmt`
  and `just verify`.
- **The packages of a lab** are fresh clones from GitHub, in the folder
  `packages` of the workspace. So the result follows the main branch of each
  profile on GitHub, and the labs need the network. There are two exceptions:
  - agent_gest_git_skills is this checkout, with its uncommitted changes.
  - jnterfaces is the clone in `JNTERFACES_DIR`.
- **The Go lab** starts Git and a local Gest. It joins the `.gitignore`,
  `.envrc` and `Justfile` snippets of this repository, then runs `just verify`.

The command does not make GitHub remotes or pull requests. The labs are setup
profiles for languages, and they are not tutorials for the flow of a pull
request.

Each lab must show these results:

- Git starts in the folder.
- The `Justfile` gives a stable command contract.
- `just verify` runs the checks for lint, types, tests and diff.

## Python, TypeScript and Rust

Each of these labs runs the steps of
[Start a Python, TypeScript or Rust project](https://rahuldave.github.io/jnterfaces/new-project.html):

```bash
git init
uv run "$JNTERFACES_DIR/scripts/install_stack.py" --profile python --defaults typecheck
just fmt
just verify
```

The profiles are jnprofile-python, jnprofile-typescript and jnprofile-rust.
The lab writes no config of a tool, so a change to a profile shows up in the
lab. Each lab differs in these ways:

- **Python.** The lab adds the tool `typecheck`. The code is `hello.py`, and
  the test is `tests/test_hello.py`.
- **TypeScript.** The lab adds the tool `test`. The code and the test are in
  `src/`. The test imports `./hello.js`, the name that the build writes.
- **Rust.** The lab is a library. It runs `cargo init --lib --vcs none` before
  the install, so `cargo init` names the package after the folder, `hello-rust`. It runs
  `just setup` first, to make `Cargo.lock`. Each item has a doc comment,
  because `docstring-check` fails on an item with none.

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
git -c init.defaultBranch=main init
gest init --local
direnv allow .
direnv exec . just verify
```

The lab copies `go.just` from the `just` skill of jnterfaces as its `Justfile`.
Its recipes are `fmt`, `lint`, `typecheck`, `build`, `test`, `docs`, `smoke`
and `diff-check`. `verify` depends on all of them except `docs`. The template
holds the tool that each recipe runs.

Lesson: `GOCACHE` must be an absolute path. In a recipe of `just`,
`$PWD/.local/go-build` gives that path. No profile covers Go, so the recipes
of the template are the only recipes.

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
