# GSU TypeScript hello world lab

The lab tries the concepts of `gsu` on a tiny TypeScript project, and you can
throw it away after. Use it to prove the setup surface before you do real work
in a target repository. The setup surface is the set of files and `just`
targets that `gsu` sets up.

The `typescript` profile owns the tools of the language. A profile is the setup
package of one language, here jnprofile-typescript. The installer of jnterfaces
installs it. The lab writes no tool config and no recipe of a tool by hand.

## Create the repo

```bash
jnterfaces=/path/to/jnterfaces
lab=/tmp/gsu-typescript-hello
rm -rf "$lab"
mkdir -p "$lab"
cd "$lab"
git init -b main
uv run "$jnterfaces/scripts/install_stack.py" --target "$lab" --profile typescript --defaults tasker
just install test
```

The installer makes `package.json`, adds the default tools of the profile, and
writes the starter `Justfile`. It saves the profile and the tools in
`.agents/stack.json`. `just install test` adds the `test` tool, which is not a
default tool.

Create `src/index.ts`:

```ts
export function greet(name = "world"): string {
  return `Hello, ${name}!`;
}
```

Create `src/index.test.ts`:

```ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { greet } from "./index.js";

test("greet defaults to the world", () => {
  assert.equal(greet(), "Hello, world!");
});

test("greet accepts a name", () => {
  assert.equal(greet("Gest"), "Hello, Gest!");
});
```

The test imports the code with the `.js` name that the build writes.

## Read the command contract

Run `just` alone to list the recipes. The profile gives these recipes:

- Setup: `just setup` installs the packages of `package.json`.
- Format: `just fmt` changes the files to the house format.
- Lint: `just lint` checks the lint rules and the format.
- Typecheck: `just typecheck` checks the types.
- Build: `just build` compiles `src` into `dist`.
- Tests: `just test [target]` builds, then runs the tests.
- Full verification: `just verify` runs `lint`, `typecheck` and `test`, then
  `git diff --check`.
- All the steps: `just check` runs the steps of the commit gate.

Map each concept to its recipe in the command contract of `AGENTS.md`. Add a
recipe to the `Justfile` only for a concept that no profile has, such as a
smoke check of the program.

## Verify

```bash
just --list
just setup
just fmt
just lint src/index.ts
just test
just verify
just check
```

Expected result:

- `just setup` installs the dependencies, with `.local/npm-cache` as the npm
  cache.
- `just lint src/index.ts` proves that a target passes a path argument to the
  tool.
- `just verify` and `just check` pass.

## Lessons for GSU

- If the setup must give the same result on each machine, keep the npm cache
  in the project. The profile does that.
- Keep the choice of tools in the profile and `.agents/stack.json`. Then the
  reusable skills name only recipes, and stay free of any one language.
