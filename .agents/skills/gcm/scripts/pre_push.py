"""The pre-push hook of the tasker role: `just ci`, less the work that a pass of `just check` already did.

The pre-commit framework runs this script for the stage pre-push. Before, the hook ran `just ci`, and in a large
project that runs again what `just check` ran for the commit gate. The script runs `just ci` as before, unless it can
prove that a pass of `just check` ran each recipe of `just ci` on the same files. Then it runs only the rest, and
prints one line that says why.

The proof has these parts. When a part fails, the script runs `just ci`, and its line says which part failed:

1. The framework names the pushed commit in `PRE_COMMIT_TO_REF`. The framework reads only the first branch of a
   push, so the commit is the tip of that branch. A push of a new history gives no commit, and gets `just ci`.
2. The tree of the worktree is the tree of that commit. So the Justfile that the script reads is the Justfile of the
   pushed commit.
3. The run log holds a pass for that tree, with each step of the `.agents/stack.json` of the commit, as the commit
   gate reads it. The line `jlog pass` of the same run ran in `just check`, as the run log shows it.
4. `just --dump` gives the recipes. `ci` is a recipe with no parameter and no line of its own, so all its work is in
   its dependencies. `check` is a recipe too.
5. A dependency of `ci` is done when the same dependency, with no arguments, is a dependency of `check` before
   its lines, or a dependency of such a dependency. A pass means that just ran each of them to the end. A dependency
   of `check` after `&&` runs after `jlog pass`, so it is not done. The search does not go into a dependency with
   arguments, since an argument can name a parameter.
6. No recipe of `ci` or `check`, or of their dependencies, names a recipe of a module, such as `sub::foo`. The dumps
   of just give such a name as `foo`, so the script reads the headers in the Justfile and in each file that it
   imports.

`ci-gate` always runs: it checks the trailers of the pushed commits, and a pass of `just check` came before the last
commit. So a dependency of `ci` that may run `ci-gate`, as a dependency or in a line, runs too.

The proof trusts the run log, as the commit gate does, and a recipe whose result does not depend only on the files of
the tree, such as a recipe that reads the commits or the environment. CI runs all of `just ci`, so it checks again what
the hook skips. Each dependency that is not done runs as `just NAME`, in the order of `ci`, with the environment of the hook.
A dependency with arguments that is not done gets `just ci`. The script exits with the status of the first recipe
that fails, or with 0.

CI does not use this script. It runs `just ci`, all of it.

Usage: pre_push.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Dict, List, Mapping, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import commit_gate as gate  # noqa: E402

# The recipe that checks the trailers. It always runs.
CI_GATE = "ci-gate"


class Unproved(Exception):
    """A reason to run all of `just ci`."""


def recipes_of(root: Path) -> Dict[str, dict]:
    """The recipes of the Justfile of ROOT, from `just --dump`, by name. An alias named `ci` or `check` makes the
    proof fail, since the dump gives an alias no dependencies."""
    run = subprocess.run(["just", "--dump", "--dump-format", "json"], cwd=root, env=gate.plain_env(),
                         stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if run.returncode != 0:
        raise Unproved("`just --dump` fails")
    try:
        dump = json.loads(run.stdout)
    except ValueError:
        raise Unproved("`just --dump` gives no JSON") from None
    recipes = dump.get("recipes") if isinstance(dump, dict) else None
    aliases = dump.get("aliases") if isinstance(dump, dict) else None
    if not isinstance(recipes, dict):
        raise Unproved("`just --dump` gives no recipes")
    if isinstance(aliases, dict) and ({"ci", "check"} & set(aliases)):
        raise Unproved("`ci` or `check` is an alias")
    return recipes


def dependencies(recipe: object) -> List[Tuple[str, bool]]:
    """Each dependency of RECIPE, as its name and True when it has arguments."""
    found = recipe.get("dependencies") if isinstance(recipe, dict) else None
    if not isinstance(found, list):
        raise Unproved("a recipe of the dump has no list of dependencies")
    out = []
    for dep in found:
        if not (isinstance(dep, dict) and isinstance(dep.get("recipe"), str)):
            raise Unproved("a dependency of the dump has no name")
        out.append((dep["recipe"], dep.get("arguments") != []))
    return out


def closure(recipes: Mapping[str, dict], names: List[str]) -> Set[str]:
    """The names of NAMES and of each recipe that they run with no arguments, as dependencies and theirs."""
    done: Set[str] = set()
    todo = list(names)
    while todo:
        name = todo.pop()
        if name in done:
            continue
        done.add(name)
        recipe = recipes.get(name)
        if recipe is not None:
            todo += [dep for dep, has_arguments in dependencies(recipe) if not has_arguments]
    return done


def done_by_check(recipes: Mapping[str, dict]) -> Set[str]:
    """The names of the recipes that `check` runs with no arguments before its own lines, and their dependencies.
    A dependency of `check` after `&&` runs after `jlog pass`, so a pass does not show that it passed. A dependency
    after `&&` of another recipe runs before `check` goes on, so it counts."""
    check = recipes["check"]
    priors = check.get("priors")
    if not isinstance(priors, int):
        raise Unproved("the recipe `check` of the dump has no count of its first dependencies")
    first = [name for name, has_arguments in dependencies(check)[:priors] if not has_arguments]
    return closure(recipes, first)


def justfiles(root: Path) -> List[Path]:
    """The Justfile of ROOT and each file that it imports, and that those import, from their `import` lines. A file
    that the script cannot read makes the proof fail, except a missing file of `import?`."""
    found: List[Path] = []
    for name in ("justfile", "Justfile", ".justfile"):
        if (root / name).is_file():
            found.append(root / name)
            break
    if not found:
        raise Unproved("the script finds no Justfile")
    index = 0
    while index < len(found):
        try:
            text = found[index].read_text(errors="replace")
        except OSError:
            raise Unproved(f"the script cannot read {found[index]}") from None
        for line in text.splitlines():
            if not line.startswith("import"):
                continue
            match = IMPORT.match(line)
            # A line that may be an import of another form, such as an x-string, a triple quote or a path from ~,
            # makes the proof fail, since the script cannot tell its file.
            # A `\` in a path of double quotes is an escape that just reads, so the file may have another name.
            if match is None or match.group(3).startswith("~") or "\\" in match.group(3):
                if re.match(r"import\??(\s|['\"x]|$)", line):
                    raise Unproved(f"the script cannot read the import line {line.strip()!r}")
                continue
            if match:
                path = (found[index].parent / match.group(3)).resolve()
                if not path.is_file():
                    if match.group(1):
                        continue
                    raise Unproved(f"the script cannot read the import {match.group(3)}")
                if path not in found:
                    found.append(path)
        index += 1
    return found


# An import line of a Justfile: `import 'file'` or `import? "file"`.
IMPORT = re.compile(r"""^import(\?)?\s+(['"])([^'"]*)\2\s*(?:#.*)?$""")


def module_names(root: Path, names: Set[str]) -> Set[str]:
    """The names of NAMES whose header, in the Justfile or a file that it imports, holds `::`, so that a dependency
    can be a recipe of a module, such as `sub::foo`. The dumps of just give such a dependency as `foo` alone, so the
    script reads the headers in the files. A header that goes on to the next line counts too."""
    odd: Set[str] = set()
    for path in justfiles(root):
        for line in path.read_text(errors="replace").splitlines():
            match = HEADER.match(line)
            if match and match.group(1) in names and ("::" in line or line.rstrip().endswith("\\")):
                odd.add(match.group(1))
    return odd


# The start of the header of a recipe: its name at the start of a line, with an optional `@`.
HEADER = re.compile(r"^@?([A-Za-z_][A-Za-z0-9_-]*)(?=[\s:])")


def runs_ci_gate(recipes: Mapping[str, dict], name: str) -> bool:
    """True when the recipe NAME may run ci-gate: a dependency of it, with or without arguments, is ci-gate, or a
    line of a recipe that it runs names ci-gate."""
    seen: Set[str] = set()
    todo = [name]
    while todo:
        current = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        recipe = recipes.get(current)
        if current == CI_GATE or (recipe is not None and CI_GATE in json.dumps(recipe.get("body"))):
            return True
        if recipe is not None:
            todo += [dep for dep, _ in dependencies(recipe)]
    return False


def check_pass(folders: List[Path], tree: str, steps: List[str]) -> bool:
    """True when a run log holds a pass for TREE that covers each step, and the line `jlog pass` of the same run ran
    in `just check`, with no other argument. So the pass came from the recipe `check`, whose dependencies the plan
    reads, and not from another recipe or from `jlog pass` by hand."""
    for folder in folders:
        try:
            lines = (folder / gate.RUN_LOG).read_text(errors="replace").splitlines()
        except OSError:
            continue
        passes: Set[str] = set()
        by_check: Set[str] = set()
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict) or not isinstance(record.get("run"), str) or not record["run"]:
                continue
            if (record.get("kind") == "pass" and record.get("tree") == tree and isinstance(record.get("steps"), list)
                    and set(steps) <= set(record["steps"])):
                passes.add(record["run"])
            argv = record.get("argv")
            if (record.get("kind") == "line" and record.get("line") == "jlog pass" and record.get("exit") == 0
                    and isinstance(argv, list) and len(argv) == 2 and isinstance(argv[0], str)
                    and os.path.basename(argv[0]) == "just" and argv[1] == "check"):
                by_check.add(record["run"])
        if passes & by_check:
            return True
    return False


def plan(root: Path, env: Mapping[str, str]) -> Tuple[str, List[str], List[str]]:
    """The tree of the pushed commit, the dependencies of `ci` that a pass of `just check` did, and the ones to run.
    Unproved stops the plan with the reason."""
    pushed = env.get("PRE_COMMIT_TO_REF")
    if not pushed:
        raise Unproved("the hook names no pushed commit, as for a push of a new history")
    commit = gate.resolve(root, pushed)
    if commit is None:
        raise Unproved(f"the pushed commit {pushed} is not a commit")
    tree = gate.git(["rev-parse", f"{commit}^{{tree}}"], root, gate.plain_env()).strip()
    if gate.worktree_tree(root) != tree:
        raise Unproved("the worktree is not the tree of the pushed commit")
    try:
        steps = gate.load_stack(gate.read_at(root, commit, gate.STACK))["steps"]
    except gate.Stop as stop:
        raise Unproved(str(stop)) from None
    if not check_pass(gate.log_folders(root), tree, steps):
        raise Unproved(f"the run log holds no pass of `just check` for the tree {tree[:12]}")
    recipes = recipes_of(root)
    ci, check = recipes.get("ci"), recipes.get("check")
    if not isinstance(ci, dict) or not isinstance(check, dict):
        raise Unproved("the Justfile has no recipe `ci` or no recipe `check`")
    if ci.get("body") != [] or ci.get("parameters") != []:
        raise Unproved("the recipe `ci` has lines or parameters of its own")
    done = done_by_check(recipes)
    odd = module_names(root, closure(recipes, ["ci", "check"]))
    if odd:
        raise Unproved(f"the recipe `{odd.pop()}` names a recipe of a module")
    covered, rest = [], []
    for name, has_arguments in dependencies(ci):
        if name in covered or name in rest:
            continue
        # A dependency that runs ci-gate must run, since the pass came before the last commit.
        if name != CI_GATE and not has_arguments and name in done and not runs_ci_gate(recipes, name):
            covered.append(name)
        elif has_arguments:
            raise Unproved(f"the dependency `{name}` of `ci` has arguments")
        else:
            rest.append(name)
    if not covered:
        raise Unproved("`just check` runs no dependency of `ci` but ci-gate")
    return tree, covered, rest


def run_just(root: Path, args: List[str]) -> int:
    return subprocess.run(["just", *args], cwd=root, stdin=subprocess.DEVNULL).returncode


def main() -> int:
    try:
        root = Path(gate.git(["rev-parse", "--show-toplevel"], Path.cwd(), gate.plain_env()).strip())
    except gate.Stop as stop:
        print(f"pre-push: {stop}", file=sys.stderr)
        return 1
    try:
        tree, covered, rest = plan(root, os.environ)
    except (Unproved, gate.Stop) as reason:
        print(f"pre-push: runs all of just ci, since {reason}", file=sys.stderr)
        return run_just(root, ["ci"])
    print(f"pre-push: the pass of just check for the tree {tree[:12]} ran {', '.join(covered)}, so the hook runs only "
          f"{', '.join(rest) or 'nothing'} of just ci", file=sys.stderr)
    for name in rest:
        status = run_just(root, [name])
        if status != 0:
            return status
    return 0


if __name__ == "__main__":
    sys.exit(main())
