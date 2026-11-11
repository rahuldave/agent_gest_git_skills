# GSU TypeScript hello world lab

The lab tries the concepts of `gsu` on a tiny TypeScript project, and you can
throw it away after. Use it to prove the setup surface before you do real work
in a target repository. The setup surface is the set of files and `just`
targets that `gsu` sets up.

## Create the repo

```bash
jnterfaces=/path/to/jnterfaces
lab=/tmp/gsu-typescript-hello
rm -rf "$lab"
mkdir -p "$lab/src"
cd "$lab"
git init -b main
uv run "$jnterfaces/scripts/install_stack.py" --target "$lab" --defaults tasker
```

Create `package.json`:

```json
{
  "name": "gsu-typescript-hello",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "build": "tsc",
    "format": "biome format --write .",
    "lint": "biome check .",
    "test": "tsc && node --test dist/*.test.js",
    "typecheck": "tsc --noEmit",
    "start": "node dist/index.js"
  },
  "devDependencies": {
    "@biomejs/biome": "^2.4.14",
    "@types/node": "^25.0.0",
    "typescript": "^5.9.3"
  }
}
```

Create `tsconfig.json`:

```json
{
  "compilerOptions": {
    "declaration": true,
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "target": "ES2022"
  },
  "include": ["src/**/*.ts"]
}
```

Create `biome.json`:

```json
{
  "formatter": {
    "enabled": true,
    "indentStyle": "space",
    "indentWidth": 2
  },
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": true
    }
  }
}
```

Create `.gitignore`:

```gitignore
node_modules/
dist/
coverage/
.local/
.env
.DS_Store
```

Create `src/index.ts`:

```ts
export function greet(name = "world"): string {
  return `Hello, ${name}!`;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  console.log(greet());
}
```

Create `src/index.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import { greet } from "./index.js";

test("greet defaults to the world", () => {
  assert.equal(greet(), "Hello, world!");
});

test("greet accepts a name", () => {
  assert.equal(greet("Gest"), "Hello, Gest!");
});
```

## Add the command contract

Create `Justfile`:

```just
export npm_config_cache := ".local/npm-cache"

default:
  just --list

setup:
  npm install

fmt path="src package.json tsconfig.json":
  npm exec -- biome format --write {{path}}

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

dev:
  npm exec -- tsc
  npm run start
```

Replace the template placeholders in `AGENTS.md`, so that the file maps setup,
format, lint, typecheck, build, test, smoke, verify and dev to the `just`
targets. For this lab, it is enough to add a concrete section at the end:

````md
## Lab Command Contract

Use the `Justfile` as the stable command interface:

```bash
just setup
just fmt [path]
just lint [path]
just typecheck
just build
just test [target]
just smoke
just verify
just dev
git diff --check
```

Mappings:

- Setup: `just setup`, which runs `npm install` with `.local/npm-cache`.
- Format: `just fmt [path]`, which runs Biome format.
- Lint: `just lint [path]`, which runs Biome check.
- Typecheck: `just typecheck`, which runs `tsc --noEmit`.
- Build: `just build`, which runs `tsc`.
- Tests: `just test [target]`, which compiles then runs `node --test`.
- Smoke: `just smoke`, which compiles then runs the hello-world program.
- Diff hygiene: `just diff-check`, which runs `git diff --check`.
- Full verification: `just verify`, which depends on `lint`, `typecheck`,
  `build`, `test`, `smoke`, and `diff-check`.
````

## Verify

```bash
just --list
just setup
just lint src/index.ts
just typecheck
just test
just verify
```

Expected result:

- `just setup` installs the dependencies, with `.local/npm-cache` as the npm cache.
- `just lint src/index.ts` proves that a target passes a path argument to the
  tool.
- `just verify` runs lint, typecheck, build, tests, smoke and diff hygiene
  through the native dependencies of Just.

## Lessons for GSU

- If the setup must give the same result on each machine, prefer an npm cache
  in the project.
- Include `@types/node` in a TypeScript project that targets Node.
- Limit the default paths of lint to the source and config files. Then lint
  does not check the generated output in `dist/` by default.
- Keep the choice of tools in `AGENTS.md` and the `Justfile`. Then the reusable
  skills stay free of any one language.
