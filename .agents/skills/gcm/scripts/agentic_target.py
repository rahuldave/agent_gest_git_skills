"""The agentic targets of the commit gates: `just review`, `just test-review`, `just update-docs`, `just prose`,
`just visual-check` and `just visualize`.

`agentic_target.py render TARGET [ARGS...]` prints an `AGENT_TASK v1` packet for a fresh agent. `jagt render` writes
the packet, with a nonce, and saves the packet file in `packets/` of the shared log folder. The record of the result
comes later, from the `SubagentStop` hook or from `just record`.

The prompt of the packet has three layers, in this order:

1. The base task: `references/targets/TARGET.md` in the one installed skill that has it, for example the `grv`
   skill for `review` or the `nossaifd` skill for `prose`.
2. A language layer for each language of `.agents/stack.json`: `.agents/targets/LANGUAGE/TARGET.md`, when the
   profile of the language ships it. The languages are the names in `profiles`, then the keys of `code` that
   `profiles` does not name.
3. The repository text: `.agents/targets/TARGET.md`, when the repository has it.

jagt 0.6.4 and later adds the language layers of `profiles` and the repository text itself, after the prompt that
the script gives. So with that jagt, the script gives only the base task, the language layers of the other keys of
`code`, and the form of the result, and each layer is in the packet once. With an older jagt, the script gives
each layer itself.

The form of the result names each field that `jagt result lint` needs, such as `follow_up`. A result without one of
these fields gives no record. It comes after the layers that the script gives, so with jagt 0.6.4 and later the
layers of jagt come after it.

The input is the diff of the worktree against HEAD, with the files that git does not track yet and does not
ignore. The tree of the worktree comes from a copy of the index, as in the gate, so a file that the index holds
counts even when `.gitignore` names it. The diff is in `diffs/HEAD-TREE.diff` of the shared log folder, where HEAD
is the commit of HEAD, or `none`, and TREE is the worktree tree.

It exits with 0 when it printed the packet, and with 1 when not.
"""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Sequence, Tuple

# What the fresh agent of each target may do, in the packet. A target that changes files names the files.
ALLOWED: Dict[str, Tuple[str, ...]] = {
    "review": ("read any file of the repository", "run commands and tests that change no file of the repository"),
    "test-review": ("read any file of the repository", "run commands and tests that change no file of the repository"),
    "update-docs": ("read any file of the repository", "change the docs that the change affects"),
    "prose": ("read any file of the repository", "change the pages and the docstrings of the change",
              "run the checkers of the pages"),
    "visual-check": ("read any file of the repository", "start and stop the app", "drive a browser",
                     "write screenshots in a temporary folder outside the repository"),
    "visualize": ("read any file of the repository", "write the diagram file and change the doc that shows it"),
}

# The required outputs of each target: the fields of `outputs` in the result.
TARGETS: Dict[str, Tuple[str, ...]] = {
    "review": ("findings",),
    "test-review": ("findings",),
    "update-docs": ("files", "checked"),
    "prose": ("files",),
    "visual-check": ("screenshots", "steps"),
    "visualize": ("files",),
}

# The form of the result, after the layers that the script gives. jagt result lint refuses a block that has no
# `follow_up`, and a base task can leave it out, so the script adds the form to each packet.
RESULT_FORM = """## The form of the result

End with one `AGENT_RESULT v1` block, in this form. The block must have each of the fields `target`, `nonce`,
`status`, `outputs`, `verification` and `follow_up`. `jagt result lint` refuses a block that does not have one of
these fields, and then the result gives no record. `follow_up` is a list of the work that is left for later, for
example `- Rename the helper in a later change.` When no work is left, it is `[]`. The rules that follow
this form, when there are any, add to the task. The result keeps this form.

    <<<AGENT_RESULT v1>>>
    target: {target}
    nonce: <the nonce of this packet>
    status: success
    outputs:
{outputs}
    verification: []
    notes: none
    follow_up: []
    <<<END_AGENT_RESULT>>>
"""

STACK = ".agents/stack.json"
# The first jagt that adds the language layers of `profiles` and the repository text to the prompt itself.
JAGT_LAYERS = (0, 6, 4)
# A plain language name, as jagt reads it: a letter or a digit, then letters, digits, `_`, `.` and `-`.
LANGUAGE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
# The install of jagt that the hint gives: the release binary first, the build from source second.
JAGT_INSTALL = ("`curl -fsSL https://raw.githubusercontent.com/rahuldave/jagt/7ea80a99492fe5eed5d7fa9b9a4e1ba08599463a/scripts/install.sh | sh -s -- --tag v0.6.3`, "
                "then put ~/.local/bin on PATH. To build it from source instead, run `cargo install --locked --git "
                "https://github.com/rahuldave/jagt --tag v0.6.3 jagt`")


class Stop(Exception):
    """A reason to print no packet."""


def git_bytes(args: Sequence[str], cwd: Path, env: Optional[Dict[str, str]] = None, check: bool = True) -> bytes:
    run = subprocess.run(["git", *args], cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True)
    if check and run.returncode != 0:
        raise Stop(f"git {' '.join(args)} failed: {run.stderr.decode(errors='replace').strip()}")
    return run.stdout if run.returncode == 0 else b""


def git(args: Sequence[str], cwd: Path, env: Optional[Dict[str, str]] = None, check: bool = True) -> str:
    return git_bytes(args, cwd, env, check).decode(errors="surrogateescape")


def alternate(path: Path) -> str:
    """`path` as an entry of GIT_ALTERNATE_OBJECT_DIRECTORIES. Git splits the list at each `:`, and reads an entry
    that starts with `"` as a C string, so a path with `:`, `"` or `\\` goes in quotes."""
    text = str(path)
    if ":" in text or '"' in text or "\\" in text:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def plain_env() -> Dict[str, str]:
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    return env


def shared_log(root: Path) -> Path:
    """The `.agents/log/` of the main checkout, which every worktree shares. A repository whose git folder is not
    `.git`, as `git init --separate-git-dir` makes it, has no main checkout that the gate and jagt agree on."""
    common = (root / git(["rev-parse", "--git-common-dir"], root, plain_env()).strip()).resolve()
    if common.name != ".git":
        raise Stop(f"the git folder {common} is not named .git, so the agentic targets do not know the shared log "
                   f"folder")
    # In the main checkout, a .git that is a link would put the log folder outside the repository.
    git_dir = (root / git(["rev-parse", "--git-dir"], root, plain_env()).strip()).resolve()
    if git_dir == common and common.parent != root.resolve():
        raise Stop(f"the git folder {common} is not in {root}, so the agentic targets do not write the shared log "
                   f"folder")
    return common.parent / ".agents/log"


def worktree_diff(root: Path) -> Tuple[str, str, bytes]:
    """The commit of HEAD, or `none`, the worktree tree, and the diff of the worktree against HEAD, as bytes. They
    come from a copy of the index and a temporary object store, as in the gate, so neither the real index nor
    `.git/objects` changes. The diff ignores the diff settings of the person and of the repository."""
    env = plain_env()
    objects = Path(git(["rev-parse", "--git-path", "objects"], root, env).strip())
    real_index = Path(git(["rev-parse", "--git-path", "index"], root, env).strip())
    with tempfile.TemporaryDirectory(prefix="agentic-target-") as temp:
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
        head = git(["rev-parse", "--verify", "--quiet", "HEAD^{commit}"], root, env, check=False).strip()
        copied = False
        if (root / real_index).is_file():
            # copy2 keeps the time of the index, which git needs to see a file that changed in the same second.
            shutil.copy2(root / real_index, index)
            listing = git(["ls-files", "-v"], root, env, check=False)
            # An assume-unchanged entry (a small letter) or a skip-worktree entry (S) hides changes from git add.
            copied = not any(line[:1].islower() or line[:1] == "S" for line in listing.splitlines())
        if not copied:
            index.unlink(missing_ok=True)
            if head:
                git(["read-tree", "HEAD"], root, env)
        git(["add", "-A", "--", ":/"], root, env)
        tree = git(["write-tree"], root, env).strip()
        base = head or git(["hash-object", "-t", "tree", "-w", "--stdin"], root, env).strip()
        diff = git_bytes(["-c", "diff.noprefix=false", "-c", "diff.mnemonicPrefix=false", "diff", "--binary",
                          "--no-color", "--no-ext-diff", "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/",
                          base, tree], root, env)
    return head or "none", tree, diff


def base_task(root: Path, target: str) -> Path:
    """The base task of the target: `references/targets/TARGET.md` in the one installed skill that has it."""
    found = sorted((root / ".agents/skills").glob(f"*/references/targets/{target}.md"))
    if not found:
        raise Stop(f"no installed skill has references/targets/{target}.md: run `just install`")
    if len(found) > 1:
        names = ", ".join(path.parts[-4] for path in found)
        raise Stop(f"two skills have references/targets/{target}.md ({names}); remove one")
    return found[0]


def stack(root: Path) -> Dict[str, object]:
    """The content of `.agents/stack.json`, or an empty dict when the file is missing or is not a JSON object."""
    try:
        content = json.loads((root / STACK).read_text())
    except (OSError, ValueError):
        return {}
    return content if isinstance(content, dict) else {}


def plain_names(names: object) -> List[str]:
    """The plain language names of a list or of the keys of a dict, in their order, each name once."""
    found: List[str] = []
    for name in names if isinstance(names, (list, dict)) else ():
        if isinstance(name, str) and LANGUAGE_NAME.fullmatch(name) and name not in found:
            found.append(name)
    return found


def languages(root: Path) -> Tuple[List[str], List[str]]:
    """The languages of the project, from `.agents/stack.json`: the names in `profiles`, which jagt 0.6.4 and later
    reads, and the keys of `code` that `profiles` does not name, which only this script reads."""
    content = stack(root)
    profiles = plain_names(content.get("profiles"))
    code = content.get("code")
    # A key of code keeps the rule that the script had before jagt read profiles: any name that is one folder, such
    # as c++. jagt reads no key of code, so a stricter rule would drop its layer.
    keys = [name for name in code if isinstance(name, str) and "/" not in name and "\\" not in name
            and name not in ("", ".", "..")] if isinstance(code, dict) else plain_names(code)
    others: List[str] = []
    for name in keys:
        if name not in profiles and name not in others:
            others.append(name)
    return profiles, others


def jagt_adds_layers(jagt: str = "jagt") -> bool:
    """True when the jagt on PATH adds the language layers of `profiles` and the repository text itself, as jagt
    0.6.4 and later does. A version that cannot be read counts as an older jagt, so the script gives each layer and
    drops none. jagt is the path of the program, the same path that the render runs."""
    try:
        printed = subprocess.run([jagt, "--version"], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                 errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    found = re.match(r"jagt (\d+)\.(\d+)\.(\d+)", printed.stdout.strip()) if printed.returncode == 0 else None
    return bool(found) and tuple(int(part) for part in found.groups()) >= JAGT_LAYERS


def layer_file(root: Path, relative: str) -> Optional[Path]:
    """The layer file `root/relative` when it has text, or None when it is missing or holds only blank lines, as jagt
    reads a layer. A file whose real path is outside `.agents/targets` stops the render, as in jagt, so a link cannot
    put another file into the packet."""
    path = root / relative
    if not path.exists():
        return None
    # As in jagt, only the root is a real path, so a link at .agents/targets leads outside it too.
    targets = root.resolve() / ".agents/targets"
    try:
        path.resolve().relative_to(targets)
    except ValueError:
        raise Stop(f"{relative} leads outside .agents/targets, so the packet does not hold it")
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError) as exc:
        raise Stop(f"cannot read {path}: {exc}")
    return path if text.strip() else None


def file_id(path: Path) -> Tuple[int, int]:
    """The device and the inode of the file that path leads to, the same for each name of one file."""
    info = path.stat()
    return info.st_dev, info.st_ino


def prompt(root: Path, target: str, jagt_layers: bool) -> Tuple[str, List[str]]:
    """The text of the prompt, and the paths of its layers, relative to the root. jagt_layers says whether jagt adds
    the language layers of `profiles` and the repository text itself; then the prompt leaves them out."""
    profiles, others = languages(root)
    names = others if jagt_layers else profiles + others
    relatives = [f".agents/targets/{name}/{target}.md" for name in names]
    if not jagt_layers:
        relatives.append(f".agents/targets/{target}.md")
    # The files that jagt reads itself. A name that differs only in case, on a disk that ignores case, or a link
    # can give the same file a second name, so the script compares the files and not the names.
    seen = set()
    if jagt_layers:
        for relative in [f".agents/targets/{name}/{target}.md" for name in profiles] + [f".agents/targets/{target}.md"]:
            path = layer_file(root, relative)
            if path is not None:
                seen.add(file_id(path))
    layers = [base_task(root, target)]
    for relative in relatives:
        path = layer_file(root, relative)
        if path is not None and file_id(path) not in seen:
            seen.add(file_id(path))
            layers.append(path)
    parts = []
    for path in layers:
        try:
            parts.append(path.read_text().strip())
        except (OSError, UnicodeDecodeError) as exc:
            raise Stop(f"cannot read {path}: {exc}")
    outputs = "\n".join(f"      {name}: []" for name in TARGETS[target])
    parts.append(RESULT_FORM.format(target=target, outputs=outputs).strip())
    return "\n\n".join(parts) + "\n", [str(path.relative_to(root)) for path in layers]


def prepare_log(root: Path, sub: str = "diffs") -> Tuple[Path, int]:
    """The shared log folder, with a `.gitignore` that ignores all of it, and an open descriptor of its folder SUB.
    The script writes the `.gitignore` before it computes the tree, so neither the run log of jlog nor the diff file
    is in the tree of the first packet of a repository. jagt ignores the folder only after it computed its tree. The
    script opens each folder through the descriptor of its parent and follows no link, so it writes nothing outside
    the repository, even when a link appears while git computes the diff. The main checkout is the folder that holds
    the real `.git`, also when the `.git` of the main checkout is a link and the script runs in a linked worktree."""
    log = shared_log(root)
    checkout = log.parent.parent
    folder = checkout
    try:
        fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    except OSError as exc:
        raise Stop(f"cannot open the main checkout {folder}: {exc.strerror}")
    try:
        for part in (".agents", "log", sub):
            folder = folder / part
            try:
                os.mkdir(part, 0o755, dir_fd=fd)
            except FileExistsError:
                pass
            except OSError as exc:
                raise Stop(f"cannot make the folder {folder}: {exc.strerror}")
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except OSError as exc:
                if os.path.islink(folder):
                    raise Stop(f"{folder} is a link, so the agentic targets do not write in it")
                if exc.errno == errno.ENOTDIR:
                    raise Stop(f"{folder} is not a folder, so the agentic targets do not write in it")
                raise Stop(f"cannot open the folder {folder}: {exc.strerror}")
            os.close(fd)
            fd = child
            if part == "log":
                write_ignore(folder, fd)
        return log, fd
    except BaseException:
        os.close(fd)
        raise


def write_ignore(log: Path, log_fd: int) -> None:
    """Write `.gitignore` with the line `*` in the log folder, unless the folder has one."""
    try:
        fd = os.open(".gitignore", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=log_fd)
    except FileExistsError:
        if os.path.islink(log / ".gitignore") or not (log / ".gitignore").is_file():
            raise Stop(f"{log / '.gitignore'} is not a file, so the agentic targets cannot ignore the log folder")
        return
    except OSError as exc:
        raise Stop(f"cannot write {log / '.gitignore'}: {exc.strerror}")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write("*\n")
    except OSError as exc:
        # A partial file would ignore nothing, and the next run would keep it.
        try:
            os.unlink(".gitignore", dir_fd=log_fd)
        except OSError:
            pass
        raise Stop(f"cannot write {log / '.gitignore'}: {exc.strerror}")


def render(root: Path, target: str, args: Sequence[str]) -> int:
    if target not in TARGETS:
        raise Stop(f"{target} is not an agentic target; the targets are " + ", ".join(TARGETS))
    found = shutil.which("jagt")
    if not found:
        raise Stop(f"jagt is not on PATH. Install it with {JAGT_INSTALL}.")
    # One full path for the check of the version and for the render, so a relative folder in PATH cannot find two
    # programs, one in the folder of the call and one in the root.
    jagt = os.path.abspath(found)
    jagt_layers = jagt_adds_layers(jagt)
    text, layers = prompt(root, target, jagt_layers)
    log, diffs_fd = prepare_log(root)
    try:
        head, tree, diff = worktree_diff(root)
        # The same tree has another diff against another HEAD, so the name holds both.
        name = f"{head}-{tree}.diff"
        diff_file = log / "diffs" / name
        try:
            # A new file, so that a hard link at the name to a file outside the repository keeps that file.
            try:
                os.unlink(name, dir_fd=diffs_fd)
            except FileNotFoundError:
                pass
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=diffs_fd)
        except OSError as exc:
            raise Stop(f"cannot write {diff_file}: {exc.strerror}")
    finally:
        os.close(diffs_fd)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(diff)
    except OSError as exc:
        raise Stop(f"cannot write {diff_file}: {exc.strerror}")
    command = [jagt, "render", target, f"--prompt-text={text}", f"--input={diff_file}"]
    if target == "test-review":
        # The result of test-parent for this tree, which the recipe test-review writes first.
        parent_result = log / "test-parent" / f"{tree}.json"
        if parent_result.is_file() and not parent_result.is_symlink():
            command.append(f"--input={parent_result}")
        else:
            print(f"agentic target: no result of test-parent for the tree {tree}; run just test-parent",
                  file=sys.stderr)
    # The = form keeps an argument that starts with - from looking like an option of jagt.
    command += [f"--arg={arg}" for arg in args]
    command += [f"--allowed-action={action}" for action in ALLOWED[target]]
    command += [f"--required-output={output}" for output in TARGETS[target]]
    print("The layers of the prompt: " + ", ".join(layers), file=sys.stderr)
    if jagt_layers:
        print("jagt adds the language layers of profiles and the repository text; the provenance of the packet "
              "names them", file=sys.stderr)
    run = subprocess.run(command, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True,
                         errors="replace")
    sys.stdout.write(run.stdout)
    if run.returncode == 0:
        check_tree(root, run.stdout, tree)
    return run.returncode


def check_tree(root: Path, packet: str, tree: str) -> None:
    """Warn when jagt saved another input tree than the tree of the diff. The gate compares the records with the
    commit tree, which this script computes as the gate does."""
    nonce = next((line.split(":", 1)[1].strip() for line in packet.splitlines() if line.startswith("nonce:")), "")
    try:
        saved = json.loads((shared_log(root) / "packets" / f"{nonce}.json").read_text()).get("input_tree")
    except (OSError, ValueError, AttributeError):
        print(f"agentic target: jagt saved no packet file for the nonce {nonce}", file=sys.stderr)
        return
    if saved != tree:
        print(f"agentic target: jagt saved the input tree {saved}, but the worktree tree is {tree}. Two causes are "
              f"known. A file that the index holds and .gitignore names is in the worktree tree, because jagt computes "
              f"its tree from HEAD and not from the index. A file in .agents/log is in the worktree tree when "
              f".agents/log/.gitignore does not ignore it. The record of this packet may not match the commit",
              file=sys.stderr)


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or argv[0] != "render":
        print("usage: agentic_target.py render TARGET [ARGS...]", file=sys.stderr)
        return 2
    try:
        root = Path(git(["rev-parse", "--show-toplevel"], Path.cwd(), plain_env()).strip())
        return 1 if render(root, argv[1], argv[2:]) else 0
    except Stop as stop:
        print(f"agentic target: {stop}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
