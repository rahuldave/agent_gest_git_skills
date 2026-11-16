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

# A lab with a profile of jnterfaces: the profile writes the manifest, the tool configs and the Justfile, as in a
# real project. TOOLS adds the tools that the profile leaves off by default. The packages are fresh clones in the
# workspace, except two: agent_gest_git_skills is the working files of this checkout, and jnterfaces is
# $JNTERFACES_DIR.
install_lab() {
  local dir="$1"
  local profile="$2"
  shift 2

  mkdir -p "$dir"
  run "$dir" git -c init.defaultBranch=main init
  run "$dir" env SKILL_PACKAGES_DIR="$workspace/packages" uv run "$jnterfaces_dir/scripts/install_stack.py" \
    --profile "$profile" --defaults --clone "agent_gest_git_skills=$repo_root" "$@"
}

write_python_lab() {
  local dir="$workspace/hello-python"
  install_lab "$dir" python typecheck
  mkdir -p "$dir/tests"

  cat >"$dir/hello.py" <<'PYTHON'
"""The greeting of the lab."""


def greet(name: str) -> str:
    """Give the greeting for NAME, such as greet("Python") == "Hello, Python!"."""
    return f"Hello, {name}!"
PYTHON

  cat >"$dir/tests/test_hello.py" <<'PYTHON'
from hello import greet


def test_greet() -> None:
    assert greet("Python") == "Hello, Python!"
PYTHON

  run "$dir" just fmt
  run "$dir" just verify
}

write_typescript_lab() {
  local dir="$workspace/hello-typescript"
  install_lab "$dir" typescript test
  mkdir -p "$dir/src"

  cat >"$dir/src/hello.ts" <<'TYPESCRIPT'
export function greet(name: string): string {
  return `Hello, ${name}!`;
}
TYPESCRIPT

  cat >"$dir/src/hello.test.ts" <<'TYPESCRIPT'
import assert from "node:assert/strict";
import { test } from "node:test";
import { greet } from "./hello.js";

test("greet", () => {
  assert.equal(greet("TypeScript"), "Hello, TypeScript!");
});
TYPESCRIPT

  run "$dir" just fmt
  run "$dir" just verify
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
  local dir="$workspace/hello-rust"
  # A library: cargo init names the package after the folder, hello-rust.
  mkdir -p "$dir"
  run "$dir" cargo init --lib --vcs none
  install_lab "$dir" rust

  cat >"$dir/src/lib.rs" <<'RUST'
//! The greeting of the lab.

/// Gives the greeting for `name`, such as `greet("Rust") == "Hello, Rust!"`.
pub fn greet(name: &str) -> String {
    format!("Hello, {name}!")
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

  run "$dir" just setup
  run "$dir" just fmt
  run "$dir" just verify
}

require_tool git
require_tool gest
require_tool direnv
require_tool just
require_tool uv
require_tool go
require_tool cargo
require_tool rustup

echo "Running language profile labs in $workspace"
write_python_lab
write_typescript_lab
write_go_lab
write_rust_lab
echo "language profile labs passed"
