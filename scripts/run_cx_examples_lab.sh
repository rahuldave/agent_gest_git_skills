#!/usr/bin/env bash
set -euo pipefail

workspace="$(mktemp -d "${TMPDIR:-/tmp}/agent-gest-cx-examples.XXXXXX")"

if [ "${AGENT_GEST_KEEP_CX_LABS:-0}" != "1" ]; then
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

assert_contains() {
  local file="$1"
  local needle="$2"
  if ! grep -F "$needle" "$file" >/dev/null; then
    echo "expected $file to contain: $needle" >&2
    echo "--- $file ---" >&2
    cat "$file" >&2
    exit 1
  fi
}

assert_not_contains() {
  local file="$1"
  local needle="$2"
  if grep -F "$needle" "$file" >/dev/null; then
    echo "expected $file not to contain: $needle" >&2
    echo "--- $file ---" >&2
    cat "$file" >&2
    exit 1
  fi
}

write_pipeline_lab() {
  local dir="$workspace/artifact-pipeline"
  mkdir -p "$dir/data" "$dir/scripts"

  cat >"$dir/data/raw.txt" <<'EOF_RAW'
hello cx pipeline
EOF_RAW

  cat >"$dir/scripts/features.sh" <<'EOF_FEATURES'
#!/usr/bin/env bash
set -euo pipefail
tr '[:lower:]' '[:upper:]' <"$1" >"$2"
EOF_FEATURES
  chmod +x "$dir/scripts/features.sh"

  cat >"$dir/scripts/train.sh" <<'EOF_TRAIN'
#!/usr/bin/env bash
set -euo pipefail
printf 'model-bytes=%s\n' "$(wc -c <"$1")" >"$2"
cat "$1" >>"$2"
EOF_TRAIN
  chmod +x "$dir/scripts/train.sh"

  cat >"$dir/scripts/report.sh" <<'EOF_REPORT'
#!/usr/bin/env bash
set -euo pipefail
printf 'report\n' >"$2"
cat "$1" >>"$2"
EOF_REPORT
  chmod +x "$dir/scripts/report.sh"

  cat >"$dir/Justfile" <<'EOF_JUST'
set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

default: report

prepare:
  mkdir -p build models reports

features: prepare
  cx --in data/raw.txt --in scripts/features.sh --out build/features.txt -- bash scripts/features.sh data/raw.txt build/features.txt

train: features
  cx --in build/features.txt --in scripts/train.sh --out models/model.txt -- bash scripts/train.sh build/features.txt models/model.txt

report: train
  cx --in models/model.txt --in scripts/report.sh --out reports/report.txt -- bash scripts/report.sh models/model.txt reports/report.txt

clean:
  rm -rf build models reports .cx
EOF_JUST

  run "$dir" cx lint
  run "$dir" just report 2>"$dir/first.err"
  assert_contains "$dir/reports/report.txt" "HELLO CX PIPELINE"

  run "$dir" just report 2>"$dir/second.err"
  assert_contains "$dir/second.err" "up-to-date: build/features.txt"
  assert_contains "$dir/second.err" "up-to-date: models/model.txt"
  assert_contains "$dir/second.err" "up-to-date: reports/report.txt"

  printf 'changed cx pipeline\n' >"$dir/data/raw.txt"
  run "$dir" just report 2>"$dir/changed.err"
  assert_not_contains "$dir/changed.err" "up-to-date: build/features.txt"
  assert_not_contains "$dir/changed.err" "up-to-date: models/model.txt"
  assert_not_contains "$dir/changed.err" "up-to-date: reports/report.txt"
  assert_contains "$dir/reports/report.txt" "CHANGED CX PIPELINE"
}

write_c_build_lab() {
  local dir="$workspace/c-incremental-build"
  mkdir -p "$dir/include" "$dir/src"

  cat >"$dir/include/app.h" <<'EOF_HEADER'
#ifndef APP_H
#define APP_H

#define APP_GREETING "hello"
#define APP_PUNCT "!"

const char *greeting(void);

#endif
EOF_HEADER

  cat >"$dir/src/main.c" <<'EOF_MAIN'
#include <stdio.h>
#include "app.h"

int main(void) {
  printf("%s%s\n", greeting(), APP_PUNCT);
  return 0;
}
EOF_MAIN

  cat >"$dir/src/util.c" <<'EOF_UTIL'
#include "app.h"

const char *greeting(void) {
  return APP_GREETING;
}
EOF_UTIL

  cat >"$dir/Justfile" <<'EOF_JUST'
set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

default: app

prepare:
  mkdir -p build

objects: prepare
  cx --in src/main.c --in include/app.h --out build/main.o -- cc -Iinclude -c src/main.c -o build/main.o
  cx --in src/util.c --in include/app.h --out build/util.o -- cc -Iinclude -c src/util.c -o build/util.o

app: objects
  cx --in build/main.o --in build/util.o --out build/app -- cc build/main.o build/util.o -o build/app

run: app
  ./build/app

clean:
  rm -rf build .cx
EOF_JUST

  run "$dir" cx lint
  run "$dir" just app 2>"$dir/first.err"
  "$dir/build/app" >"$dir/app.out"
  assert_contains "$dir/app.out" "hello!"

  run "$dir" just app 2>"$dir/second.err"
  assert_contains "$dir/second.err" "up-to-date: build/main.o"
  assert_contains "$dir/second.err" "up-to-date: build/util.o"
  assert_contains "$dir/second.err" "up-to-date: build/app"

  sed 's/return APP_GREETING;/return APP_GREETING "-util";/' "$dir/src/util.c" >"$dir/src/util.c.tmp"
  mv "$dir/src/util.c.tmp" "$dir/src/util.c"
  run "$dir" just app 2>"$dir/util-change.err"
  assert_contains "$dir/util-change.err" "up-to-date: build/main.o"
  assert_not_contains "$dir/util-change.err" "up-to-date: build/util.o"
  assert_not_contains "$dir/util-change.err" "up-to-date: build/app"
  "$dir/build/app" >"$dir/app.out"
  assert_contains "$dir/app.out" "hello-util!"

  sed 's/APP_GREETING "hello"/APP_GREETING "header-change"/; s/APP_PUNCT "!"/APP_PUNCT "?"/' "$dir/include/app.h" >"$dir/include/app.h.tmp"
  mv "$dir/include/app.h.tmp" "$dir/include/app.h"
  run "$dir" just app 2>"$dir/header-change.err"
  assert_not_contains "$dir/header-change.err" "up-to-date: build/main.o"
  assert_not_contains "$dir/header-change.err" "up-to-date: build/util.o"
  assert_not_contains "$dir/header-change.err" "up-to-date: build/app"
  "$dir/build/app" >"$dir/app.out"
  assert_contains "$dir/app.out" "header-change-util?"
}

require_tool bash
require_tool cc
require_tool cx
require_tool grep
require_tool just
require_tool sed

echo "Running cx example labs in $workspace"
write_pipeline_lab
write_c_build_lab
echo "cx example labs passed"
