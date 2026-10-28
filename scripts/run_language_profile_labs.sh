#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# The Justfile templates are in the just skill of jnterfaces.
jnterfaces_dir="${JNTERFACES_DIR:-$repo_root/../jnterfaces}"
templates="$jnterfaces_dir/.agents/skills/just/assets/templates"
if [ ! -d "$templates" ]; then
  echo "The labs need a jnterfaces clone at $jnterfaces_dir. Clone https://github.com/rahuldave/jnterfaces there, or set JNTERFACES_DIR." >&2
  exit 1
fi
workspace="$(mktemp -d "${TMPDIR:-/tmp}/agent-gest-language-labs.XXXXXX")"

if [ "${AGENT_GEST_KEEP_LANGUAGE_LABS:-0}" != "1" ]; then
  trap 'rm -rf "$workspace"' EXIT
fi

require_tool() {
  local tool="$1"
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "missing required tool: $tool" >&2
    exit 1
  fi
}

run() {
  local dir="$1"
  shift
  printf '\n[%s] %s\n' "$(basename "$dir")" "$*"
  (cd "$dir" && "$@")
}

run_env() {
  local dir="$1"
  shift
  run "$dir" direnv exec . "$@"
}

copy_template() {
  local source="$1"
  local target="$2"
  cat "$repo_root/$source" >>"$target"
}

init_lab() {
  local dir="$1"
  local profile="$2"
  local justfile="$3"

  mkdir -p "$dir"
  copy_template "templates/gitignore/base.gitignore" "$dir/.gitignore"
  printf '\n' >>"$dir/.gitignore"
  copy_template "templates/gitignore/$profile.gitignore" "$dir/.gitignore"
  copy_template "templates/env/$profile.envrc" "$dir/.envrc"
  cp "$templates/$justfile" "$dir/Justfile"

  run "$dir" git -c init.defaultBranch=main init
  run "$dir" gest init --local
  run "$dir" direnv allow .
}

write_python_lab() {
  local dir="$workspace/python-uv"
  init_lab "$dir" "python-uv" "python-uv.just"
  mkdir -p "$dir/tests"

  cat >"$dir/pyproject.toml" <<'PYPROJECT'
[project]
name = "language-profile-python"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "pytest>=8.0.0",
  "ruff>=0.8.0",
  "ty>=0.0.1a0",
]
PYPROJECT

  cat >"$dir/hello.py" <<'PYTHON'
def greet(name: str) -> str:
    return f"Hello, {name}!"


if __name__ == "__main__":
    print(greet("Python"))
PYTHON

  cat >"$dir/tests/test_hello.py" <<'PYTHON'
from hello import greet


def test_greet() -> None:
    assert greet("Python") == "Hello, Python!"
PYTHON

  run_env "$dir" just setup
  run_env "$dir" just verify
}

write_typescript_lab() {
  local dir="$workspace/typescript-npm"
  init_lab "$dir" "typescript-npm" "typescript-npm.just"
  mkdir -p "$dir/src"

  cat >"$dir/package.json" <<'JSON'
{
  "name": "language-profile-typescript",
  "version": "0.1.0",
  "private": true,
  "type": "commonjs",
  "devDependencies": {
    "@biomejs/biome": "^2.2.0",
    "@types/node": "^24.0.0",
    "typescript": "^5.9.0"
  }
}
JSON

  cat >"$dir/tsconfig.json" <<'JSON'
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "CommonJS",
    "moduleResolution": "Node",
    "rootDir": "src",
    "outDir": "dist",
    "strict": true,
    "types": ["node"],
    "esModuleInterop": true
  },
  "include": ["src/**/*.ts"]
}
JSON

  cat >"$dir/biome.json" <<'JSON'
{
  "$schema": "https://biomejs.dev/schemas/2.2.0/schema.json",
  "formatter": {
    "enabled": false
  },
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": true
    }
  }
}
JSON

  cat >"$dir/src/index.ts" <<'TYPESCRIPT'
export function greet(name: string): string {
  return `Hello, ${name}!`;
}

if (require.main === module) {
  console.log(greet("TypeScript"));
}
TYPESCRIPT

  cat >"$dir/src/index.test.ts" <<'TYPESCRIPT'
import assert from "node:assert/strict";
import test from "node:test";
import { greet } from "./index";

test("greet", () => {
  assert.equal(greet("TypeScript"), "Hello, TypeScript!");
});
TYPESCRIPT

  run_env "$dir" just setup
  run_env "$dir" just verify
}

write_go_lab() {
  local dir="$workspace/go"
  init_lab "$dir" "go" "go.just"

  cat >"$dir/go.mod" <<'GOMOD'
module example.com/language-profile-go

go 1.22
GOMOD

  cat >"$dir/main.go" <<'GO'
package main

import "fmt"

func greet(name string) string {
	return fmt.Sprintf("Hello, %s!", name)
}

func main() {
	fmt.Println(greet("Go"))
}
GO

  cat >"$dir/main_test.go" <<'GO'
package main

import "testing"

func TestGreet(t *testing.T) {
	got := greet("Go")
	want := "Hello, Go!"
	if got != want {
		t.Fatalf("greet() = %q, want %q", got, want)
	}
}
GO

  run_env "$dir" just verify
}

write_rust_lab() {
  local dir="$workspace/rust-cargo"
  init_lab "$dir" "rust-cargo" "rust-cargo.just"
  mkdir -p "$dir/src"
  cp "$repo_root/templates/rust/rust-toolchain.toml" "$dir/rust-toolchain.toml"

  cat >"$dir/Cargo.toml" <<'CARGO'
[package]
name = "language-profile-rust"
version = "0.1.0"
edition = "2021"

[dependencies]
CARGO

  cat >"$dir/src/main.rs" <<'RUST'
fn greet(name: &str) -> String {
    format!("Hello, {name}!")
}

fn main() {
    println!("{}", greet("Rust"));
}

#[cfg(test)]
mod tests {
    use super::greet;

    #[test]
    fn greets_rust() {
        assert_eq!(greet("Rust"), "Hello, Rust!");
    }
}
RUST

  run_env "$dir" just verify
}

require_tool git
require_tool gest
require_tool direnv
require_tool just
require_tool uv
require_tool npm
require_tool go
require_tool cargo

echo "Running language profile labs in $workspace"
write_python_lab
write_typescript_lab
write_go_lab
write_rust_lab
echo "language profile labs passed"
