#!/usr/bin/env bash
# The stack installer moved to jnterfaces. This script keeps the old options and passes them to
# jnterfaces/scripts/install_stack.sh, with this clone as the Gest package.
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/install_stack.sh [OPTIONS] [--] TARGET

The stack installer is now scripts/install_stack.sh of jnterfaces. This script
passes its options there. If the target has no saved choices in
.agents/stack.json and you pass no choice options (--with, --without, --all,
--defaults or --ask), it installs the set that it installed before: the Gest
skills and all three jnterfaces skills. It adds no nossaifd, but it keeps an
installed nossaifd.

Old options:
  --with-lanes      also install sklanes (the same as --with sklanes)
  --jnterfaces DIR  clone of jnterfaces; default: ../jnterfaces next to this repository
  --sklanes DIR     clone of sklanes (the same as --clone sklanes=DIR)
  --clean, --dry-run

Every other option goes to the jnterfaces stack installer. Run it with --help to
see them.
USAGE
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
jnterfaces="$repo_root/../jnterfaces"
forward=(--clone "agent_gest_git_skills=$repo_root")
chose=0
target=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --with-lanes) forward+=(--with sklanes) ;;
    --jnterfaces) [ "$#" -ge 2 ] || { usage; exit 2; }; jnterfaces="$2"; shift ;;
    --sklanes) [ "$#" -ge 2 ] || { usage; exit 2; }; forward+=(--clone "sklanes=$2"); shift ;;
    --with|--without) [ "$#" -ge 2 ] || { usage; exit 2; }; chose=1; forward+=("$1" "$2"); shift ;;
    --clone) [ "$#" -ge 2 ] || { usage; exit 2; }; forward+=("$1" "$2"); shift ;;
    --all|--defaults|--ask) chose=1; forward+=("$1") ;;
    --) shift; [ "$#" -eq 1 ] && [ -z "$target" ] || { usage; exit 2; }; target="$1"; break ;;
    -*) forward+=("$1") ;;
    *) [ -z "$target" ] || { echo "Only one TARGET is allowed" >&2; exit 2; }; target="$1" ;;
  esac
  shift
done
[ -n "$target" ] || { usage; exit 2; }
# `[ -L link/ ]` follows the link, so test the path without its trailing slashes.
bare="$target"
while [ "$bare" != "/" ] && [ "$bare" != "${bare%/}" ]; do bare="${bare%/}"; done
[ ! -L "$bare" ] || { echo "The target repository root must not be a symlink" >&2; exit 2; }
# An absolute path keeps a target such as -odd from looking like an option.
target="$(cd -- "$target" && pwd -P)" || { echo "Target does not exist" >&2; exit 2; }
# Saved choices, or choices on the command line, win. Only a target without them gets the old set.
if [ ! -f "$target/.agents/stack.json" ] && [ "$chose" -eq 0 ]; then
  forward+=(--with gest,cx,jagt-protocol)
  # An installed nossaifd stays on. The old set had no nossaifd, so it stays off where it is not installed.
  [ -f "$target/.agents/nossaifd-install.json" ] || forward+=(--without nossaifd)
fi
stack="$jnterfaces/scripts/install_stack.sh"
if [ ! -f "$stack" ]; then
  echo "No jnterfaces clone with scripts/install_stack.sh at $jnterfaces. Clone https://github.com/rahuldave/jnterfaces there, or pass --jnterfaces DIR." >&2
  exit 1
fi
echo "Note: the stack installer is now $stack. This script passes its options there." >&2
exec bash "$stack" "$target" "${forward[@]}"
