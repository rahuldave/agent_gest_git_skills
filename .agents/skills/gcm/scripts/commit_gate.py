"""The commit gate: the git pre-commit and pre-merge-commit hooks run it before each commit.

The gate never runs a step. It reads what `just check` and the agentic targets wrote, and stops the commit when
something is missing:

1. The steps of `.agents/stack.json` and the required targets must be recipes of the Justfile.
2. The commit tree must equal the worktree tree, so all changes must be staged.
3. The run log must hold a pass of `just check` for the commit tree.
4. For a commit by an agent, the records must hold a chain of the required targets that ends at the commit tree.

The lists that exempt paths come from the parent commit, so a commit cannot change them for itself:
`.agents/targets/required.txt` and `.agents/generated.txt`. With no parent, or a parent without the file, the gate
uses the default list of required targets and an empty list of generated paths. The steps come from the
`.agents/stack.json` of the commit, as `jlog pass` reads them, so a commit can remove a tool and its step. The code
globs of `@code` come from the `.agents/stack.json` of the commit and of the parent. An amend replaces HEAD, so for
what looks like `git commit --amend` the gate applies the rules of HEAD and of its parent, and the stricter win. The
`required.txt` of the commit must be readable too, so a bad line cannot land.

Each line of `required.txt` names a target and the paths that make it required, as git pathspecs with `:(glob)`.
`@code` names the source globs of each profile, from the key `code` of `.agents/stack.json`, less the paths of
`generated.txt`. `@pages` is `**/*.md` and `**/*.qmd`. `@api` is empty until the installer writes the API packages.
Every commit needs `review`, whatever the file says.

A record is a JSON file in `records/` of the shared log folder, the `.agents/log/` of the main checkout:

    {"version": 1, "target": "review", "status": "success", "input_tree": "<tree>", "output_tree": "<tree>",
     "findings": [{"summary": "...", "test": "<the test that shows the fix>"},
                  {"summary": "...", "reason": "<why it is not fixed>"}],
     "source": "hook", "model": "<model>", "nonce": "<nonce>"}

A record counts when its status is `success` and each finding has a `test` or a `reason`. A skip from
`just record-skip` is a record with `"source": "skip"`, a `reason`, and the same tree twice.

The chain: `update-docs` comes before `prose`, and each record starts at the output tree of the record before it. The
last output tree is the commit tree. Every other target, such as `review` and `test-review`, has the commit tree as
its input tree and its output tree.

Usage: commit_gate.py [--hook pre-commit|pre-merge-commit]. It exits with 0 to let the commit through and with 1
to stop it.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

# The variables of a harness that mark a commit by an agent.
AGENT_VARIABLES = ("CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDECODE")

# The default required targets, used when the parent has no required.txt.
DEFAULT_REQUIRED = """\
review       **
test-review  @code
update-docs  @pages  @api
prose        @pages  @api
"""

# The targets that change files, in the order of the chain.
CHANGERS = ("update-docs", "prose")

PAGES = ("**/*.md", "**/*.qmd")

STACK = ".agents/stack.json"
REQUIRED = ".agents/targets/required.txt"
GENERATED = ".agents/generated.txt"
RUN_LOG = "just.jsonl"


class Stop(Exception):
    """A reason to stop the commit. The text says what to run."""


def git(args: Sequence[str], cwd: Path, env: Optional[Dict[str, str]] = None, check: bool = True) -> str:
    run = subprocess.run(["git", *args], cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                         errors="surrogateescape")
    if check and run.returncode != 0:
        raise Stop(f"git {' '.join(args)} failed: {run.stderr.strip()}")
    return run.stdout if run.returncode == 0 else ""


def alternate(path: Path) -> str:
    """`path` as an entry of GIT_ALTERNATE_OBJECT_DIRECTORIES. Git splits the list at each `:`, and reads an entry
    that starts with `"` as a C string, so a path with `:`, `"` or `\\` goes in quotes."""
    text = str(path)
    if ":" in text or '"' in text or "\\" in text:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def plain_env() -> Dict[str, str]:
    """The environment without the index of the hook, for the git calls that must not touch it."""
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    return env


def is_tree(value: object) -> bool:
    return isinstance(value, str) and len(value) in (40, 64) and all(c in "0123456789abcdef" for c in value)


def worktree_tree(root: Path) -> str:
    """The tree of the worktree, as `jlog` computes it: a temporary index and a temporary object store, so neither
    the real index nor `.git/objects` changes. Files that git ignores are not in the tree."""
    env = plain_env()
    objects = Path(git(["rev-parse", "--git-path", "objects"], root, env).strip())
    real_index = Path(git(["rev-parse", "--git-path", "index"], root, env).strip())
    with tempfile.TemporaryDirectory(prefix="commit-gate-") as temp:
        index = Path(temp) / "index"
        (Path(temp) / "objects").mkdir()
        env.update(GIT_INDEX_FILE=str(index), GIT_OBJECT_DIRECTORY=str(Path(temp) / "objects"),
                   GIT_ALTERNATE_OBJECT_DIRECTORIES=":".join(
                       filter(None, [alternate(root / objects), os.environ.get("GIT_ALTERNATE_OBJECT_DIRECTORIES", "")])))
        # With a split index, each write of the copy, by git add and by git write-tree, would leave a new shared index
        # in the git folder. A setting in the environment reaches every command on the copy.
        count = int(env.get("GIT_CONFIG_COUNT", "0") or "0")
        env.update({"GIT_CONFIG_COUNT": str(count + 1), f"GIT_CONFIG_KEY_{count}": "core.splitIndex",
                    f"GIT_CONFIG_VALUE_{count}": "false"})
        copied = False
        if (root / real_index).is_file():
            # copy2 keeps the time of the index, which git needs to see a file that changed in the same second.
            shutil.copy2(root / real_index, index)
            listing = git(["ls-files", "-v"], root, env, check=False)
            # An assume-unchanged entry (a small letter) or a skip-worktree entry (S) hides changes from git add.
            copied = not any(line[:1].islower() or line[:1] == "S" for line in listing.splitlines())
        if not copied:
            index.unlink(missing_ok=True)
            if git(["rev-parse", "--verify", "--quiet", "HEAD^{tree}"], root, env, check=False):
                git(["read-tree", "HEAD"], root, env)
        git(["add", "-A", "--", ":/"], root, env)
        return git(["write-tree"], root, env).strip()


def commit_tree(root: Path) -> str:
    """The tree of the commit: the index of the hook, from `GIT_INDEX_FILE` when git sets it."""
    return git(["write-tree"], root, dict(os.environ)).strip()


def git_argv() -> List[str]:
    """The argv of the nearest git above this process, from ps, or [] when ps cannot tell. A hook manager such as
    pre-commit can stand between git and the gate."""
    pid = os.getppid()
    for _ in range(6):
        run = subprocess.run(["ps", "-o", "ppid=", "-o", "args=", "-p", str(pid)], stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, errors="replace")
        fields = run.stdout.split()
        if run.returncode != 0 or len(fields) < 2:
            return []
        if os.path.basename(fields[1]) == "git":
            return fields[1:]
        pid = int(fields[0])
    return []


def is_amend(argv: Sequence[str]) -> bool:
    """True for `git commit --amend`, also with an abbreviation of the option that git accepts, such as `--am`. A
    message can hold the same word, so the gate then applies the rules of both possible parents."""
    return any(len(word) >= 4 and "--amend".startswith(word) for word in argv)


def resolve(root: Path, revision: str) -> Optional[str]:
    out = git(["rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}"], root, plain_env(), check=False).strip()
    return out or None


def parents_of_commit(root: Path) -> List[Optional[str]]:
    """The parents to check the commit against: HEAD, and for what looks like an amend also the parent of HEAD,
    since an amend replaces HEAD. Each one gives its own required targets, so the stricter rules win. None stands
    for no parent, as on the first commit."""
    head = resolve(root, "HEAD")
    if head is not None and is_amend(git_argv()):
        return [head, resolve(root, "HEAD^")]
    return [head]


def read_at(root: Path, revision: str, path: str) -> Optional[str]:
    """The text of PATH at REVISION, or None when it has no such file. `:` as REVISION is the index of the hook."""
    env = dict(os.environ) if revision == "" else plain_env()
    run = subprocess.run(["git", "show", f"{revision}:{path}"], cwd=root, env=env, stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, errors="surrogateescape")
    return run.stdout if run.returncode == 0 else None


def load_stack(text: Optional[str]) -> dict:
    if text is None:
        raise Stop(f"{STACK} is missing, so the gate does not know the steps: run `just install`")
    try:
        stack = json.loads(text)
    except ValueError as error:
        raise Stop(f"{STACK} is not JSON ({error}): run `just install`")
    steps = stack.get("steps") if isinstance(stack, dict) else None
    if not isinstance(steps, list) or not all(isinstance(step, str) and step for step in steps):
        raise Stop(f"{STACK} has no list `steps` of names: run `just install`")
    return stack


def list_lines(text: Optional[str]) -> List[str]:
    """The entries of a list file: one on each line, with no blank line and no `#` comment."""
    lines = (line.strip() for line in (text or "").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def parse_required(text: str) -> Dict[str, List[str]]:
    """Each target of required.txt and its paths. A target on two lines gets the paths of both. A comment goes on
    a line of its own, and a path has no pathspec magic of its own, so a `#` or a leading `:` stops the commit."""
    required: Dict[str, List[str]] = {}
    for line in list_lines(text):
        target, *paths = line.split()
        odd = [word for word in [target, *paths] if "#" in word or word.startswith(":")]
        if odd or not all(c.isalnum() or c in "-_" for c in target):
            raise Stop(f"{REQUIRED} has a line that the gate cannot read: {line!r}. Write a target name and its "
                       "paths, with a comment on a line of its own")
        required.setdefault(target, []).extend(paths)
    return required


def code_globs(stack: object) -> List[str]:
    """The source globs of each profile, from the key `code` of a stack.json."""
    code = stack.get("code") if isinstance(stack, dict) else None
    if not isinstance(code, dict):
        return []
    return [g for globs in code.values() if isinstance(globs, list) for g in globs if isinstance(g, str) and g]


def merged_code(stack: dict, parent_text: Optional[str]) -> List[str]:
    try:
        parent = json.loads(parent_text) if parent_text is not None else None
    except ValueError:
        parent = None
    globs = code_globs(parent) + code_globs(stack)
    return list(dict.fromkeys(globs))


def pathspecs(paths: Iterable[str], code: List[str], generated: List[str]) -> List[str]:
    """The git pathspecs of the paths of one target, with the aliases expanded."""
    specs: List[str] = []
    for path in paths:
        if path == "@code":
            specs += [f":(glob){g}" for g in code]
        elif path == "@pages":
            specs += [f":(glob){g}" for g in PAGES]
        elif path == "@api":
            continue
        else:
            specs.append(f":(glob){path}")
    if specs:
        specs += [f":(exclude,glob){g}" for g in generated]
    return specs


def changes_match(root: Path, parent: Optional[str], tree: str, specs: List[str]) -> bool:
    """True when the commit changes a path that the pathspecs match. A deleted path counts."""
    if not specs:
        return False
    env = plain_env()
    # On the first commit, every path is new: compare with the empty tree. ls-tree takes no glob pathspec.
    before = parent or git(["hash-object", "-t", "tree", "--stdin"], root, env).strip()
    out = git(["diff", "--name-only", "-z", "--no-renames", before, tree, "--", *specs], root, env)
    return bool(out.strip("\0"))


def recipes(root: Path) -> Set[str]:
    if shutil.which("just") is None:
        raise Stop("just is not on PATH. Install it: https://just.systems")
    run = subprocess.run(["just", "--summary"], cwd=root, env=plain_env(), stdin=subprocess.DEVNULL,
                         capture_output=True, text=True)
    if run.returncode != 0:
        raise Stop(f"just --summary failed: {run.stderr.strip()}")
    return set(run.stdout.split())


def log_folders(root: Path) -> List[Path]:
    """The log folder of this worktree, and the shared log folder of the main checkout."""
    common = Path(git(["rev-parse", "--git-common-dir"], root, plain_env()).strip())
    common = (root / common).resolve()
    folders = [root / ".agents/log"]
    if common.name == ".git" and common.parent.resolve() != root.resolve():
        folders.append(common.parent / ".agents/log")
    return folders


def has_pass(folders: List[Path], tree: str, steps: List[str]) -> bool:
    """True when a run log holds a pass of `just check` for TREE that covers each step."""
    for folder in folders:
        try:
            lines = (folder / RUN_LOG).read_text(errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if (isinstance(record, dict) and record.get("kind") == "pass" and record.get("tree") == tree
                    and isinstance(record.get("steps"), list) and set(steps) <= set(record["steps"])):
                return True
    return False


def record_counts(record: object) -> bool:
    """True for a record whose status is success and whose findings each have a test or a reason."""
    if not isinstance(record, dict) or record.get("version") != 1 or record.get("status") != "success":
        return False
    if not (isinstance(record.get("target"), str) and is_tree(record.get("input_tree"))
            and is_tree(record.get("output_tree"))):
        return False
    if record.get("source") == "skip":
        reason = record.get("reason")
        return isinstance(reason, str) and bool(reason.strip()) and record["input_tree"] == record["output_tree"]
    findings = record.get("findings", [])
    if not isinstance(findings, list):
        return False
    return all(isinstance(f, dict) and any(isinstance(f.get(key), str) and f[key].strip() for key in ("test", "reason"))
               for f in findings)


def load_records(folders: List[Path]) -> List[dict]:
    found: List[dict] = []
    for folder in folders:
        records = folder / "records"
        if not records.is_dir():
            continue
        for path in sorted(records.glob("*.json")):
            try:
                record = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if record_counts(record):
                found.append(record)
    return found


def missing_targets(required: List[str], records: List[dict], tree: str) -> List[str]:
    """The required targets with no record in a chain that ends at TREE, in the order to run them."""
    by_target: Dict[str, List[Tuple[str, str]]] = {}
    for record in records:
        by_target.setdefault(record["target"], []).append((record["input_tree"], record["output_tree"]))
    missing = [t for t in required if t not in CHANGERS and (tree, tree) not in by_target.get(t, [])]
    changers = [t for t in CHANGERS if t in required]

    def chain_ends(index: int, end: str) -> bool:
        """True when the changers up to INDEX make a chain whose last output tree is END."""
        if index < 0:
            return True
        return any(out == end and chain_ends(index - 1, start) for start, out in by_target.get(changers[index], []))

    if changers and not chain_ends(len(changers) - 1, tree):
        # A changer that runs again changes the input of each later one, so they all run again, in order.
        missing = changers + missing
    return missing


def is_agent() -> bool:
    return any(os.environ.get(name) for name in AGENT_VARIABLES)


def required_against(root: Path, parent: Optional[str], stack: dict, tree: str) -> List[str]:
    """The targets that the rules of PARENT require for the change from PARENT to TREE."""
    if parent is None:
        required_text, generated = DEFAULT_REQUIRED, []
    else:
        required_text = read_at(root, parent, REQUIRED)
        required_text = DEFAULT_REQUIRED if required_text is None else required_text
        generated = list_lines(read_at(root, parent, GENERATED))
    try:
        required_paths = parse_required(required_text)
    except Stop as stop:
        # A list from before the gate checked it. The default list applies, so the commit that fixes it can go.
        print(f"commit gate: {stop}. The gate uses the default list for this commit", file=sys.stderr)
        required_paths = parse_required(DEFAULT_REQUIRED)
    # The code globs of the parent and of the commit both count, so a commit that removes a language still needs
    # test-review for its code. A parent with no stack.json, before the gates came, gives no globs.
    code = merged_code(stack, None if parent is None else read_at(root, parent, STACK))
    return [t for t, paths in required_paths.items()
            if changes_match(root, parent, tree, pathspecs(paths, code, generated))]


def gate(root: Path) -> None:
    parents = parents_of_commit(root)
    stack_text = read_at(root, "", STACK)
    if stack_text is None and any(p is not None and read_at(root, p, STACK) is not None for p in parents):
        raise Stop(f"the commit removes {STACK}, and the gate needs it. To remove the gates, take off their hooks "
                   "first, then commit")
    # The steps come from the commit, since jlog passes the steps of the worktree. A commit that removes a tool
    # removes its step. The review of the commit sees that change.
    stack = load_stack(stack_text)
    # A line that the gate cannot read must not land, or it would stop every later commit.
    own_list = read_at(root, "", REQUIRED)
    if own_list is not None:
        parse_required(own_list)
    tree = commit_tree(root)
    required: List[str] = ["review"]
    for parent in parents:
        required += [t for t in required_against(root, parent, stack, tree) if t not in required]

    known = recipes(root)
    absent = [name for name in ["check", *stack["steps"], *required] if name not in known]
    if absent:
        raise Stop("the Justfile has no recipe " + ", ".join(f"`{name}`" for name in absent) + ": run `just install`")

    if worktree_tree(root) != tree:
        raise Stop("only part of the changes is staged, and the gate checks the whole worktree. Stage them all, or "
                   "put the rest aside: run `git stash --keep-index -u`, then `just check`, then commit, then "
                   "`git stash pop`")

    folders = log_folders(root)
    if not has_pass(folders, tree, stack["steps"]):
        raise Stop("no pass of `just check` for this tree: run `just check`")

    if is_agent():
        missing = missing_targets(required, load_records(folders), tree)
        if missing:
            raise Stop("no record for this tree of " + ", ".join(f"`just {t}`" for t in missing)
                       + ": run them in this order")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="The commit gate.")
    parser.add_argument("--hook", choices=("pre-commit", "pre-merge-commit"), default="pre-commit")
    parser.parse_args(argv)
    root = Path(git(["rev-parse", "--show-toplevel"], Path.cwd(), plain_env()).strip())
    try:
        gate(root)
    except Stop as stop:
        print(f"commit gate: {stop}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
