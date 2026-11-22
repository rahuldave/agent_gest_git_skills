"""The commit gate: the git pre-commit and pre-merge-commit hooks run it before each commit.

The gate runs one step only, `release-check`, at the commit-msg hook. It reads what `just check` and the agentic targets wrote, and stops the commit when
something is missing:

1. The steps of `.agents/stack.json` and the required targets must be recipes of the Justfile.
2. The commit tree must equal the worktree tree, so all changes must be staged.
3. The run log must hold a pass of `just check` for the commit tree.
4. For a commit by an agent, the records must hold a record of each required target that counts for the commit tree.

The lists that exempt paths come from the parent commit, so a commit cannot change them for itself:
`.agents/targets/required.txt` and `.agents/generated.txt`. With no parent, or a parent without the file, the gate
uses the default list of required targets and an empty list of generated paths. The steps come from the
`.agents/stack.json` of the commit, as `jlog pass` reads them, so a commit can remove a tool and its step. The code
globs of `@code` come from the `.agents/stack.json` of the commit and of the parent. An amend replaces HEAD, so for
what looks like `git commit --amend` the gate applies the rules of HEAD and of its parent, and the stricter win. The
`required.txt` of the commit must be readable too, so a bad line cannot land.

Each line of `required.txt` names a target and the paths that make it required, as git pathspecs with `:(glob)`.
`@code` names the source globs of each profile, from the key `code` of `.agents/stack.json`, less the paths of
`generated.txt`. `@pages` is the files that `is_page` of the nossaifd role accepts, from its `prose_gate.py` in the
parent, so `AGENTS.md` and `CHANGELOG.md` are not pages. The rule runs in a Python of its own. Without the role in
the parent, as on the first commit, `@pages` is `**/*.md` and `**/*.qmd`. `@api` is the files that `is_api` of a
language profile accepts, from its `.agents/just/<profile>/api_rule.py` in the parent. The profiles are the names of
the key `profiles` of the `.agents/stack.json` of the parent and of the commit. A profile whose parent has no rule
adds no file, and on the first commit `@api` names no file. Each rule runs in a Python of its own, as the page rule
does.
Every commit needs `review`, whatever the file says.

A record is a JSON file in `records/` of the shared log folder, the `.agents/log/` of the main checkout:

    {"version": 1, "target": "review", "status": "success", "input_tree": "<tree>", "output_tree": "<tree>",
     "findings": [{"summary": "...", "test": "<the test that shows the fix>"},
                  {"summary": "...", "reason": "<why it is not fixed>"}],
     "source": "hook", "model": "<model>", "nonce": "<nonce>"}

A record counts when its status is `success` and each finding has a `test` or a `reason`. A skip from
`just record-skip` is a record with `"source": "skip"`, a `reason`, and the same tree twice.

The scopes: a record of a tree counts for the commit tree when no path that differs between the two trees is in the
scope of its target, as SCOPES gives it. Objects compares the two trees, so each side of a rename counts, and a
deleted path counts. It reads each tree object from the folder `objects` of a log folder or from git with no replace
refs, and checks that it hashes to its ID. A path is a page, data or code, and a path whose kind is in doubt is code. A change
of a page alone keeps `review` and `test-review`, a change of data alone keeps `prose`, and every change voids
`update-docs`. A target that changes no file, such as `review`, counts by a record whose input tree is its output tree.
`update-docs` and `prose` change files, so they count by their output tree. Between the output tree of `update-docs`
and the commit tree, `prose` records may come, since `prose` changes only what it checks. A skip counts for its own
tree only. The pass of `just check` is still for the commit tree itself.

The trailer: the commit-msg hook runs the gate once more, and when it passes, it adds a trailer to the message:
`Commit-Gate: patch:<patch-id>`, or `Commit-Gate: tree:<tree>` for a merge. A patch ID is the hash of the change,
from `git patch-id --verbatim` on a diff with no lines of context, so a rebase with no conflict keeps it. With no
context, a line that moves within one part of a file keeps the ID too. The trailer is a claim, so that is a fair
price. `git commit -n` skips the commit-msg hook too, so a commit that went around the gate has no trailer. The trailer
has one word. For an amend, the patch ID is against the parent of HEAD, and an amend of a merge gets the tree. Ps
shows the words of each argument joined, so a word `--amend` after the text of `-m` may be a part of the message.
Then the gate reads each argument whole, from /proc on Linux or the sysctl KERN_PROCARGS2 on macOS, and it stops the
commit when neither can tell. An old trailer of the gate in the message goes, so an amend with `-F` has one trailer.
When git may find the message empty and stop the commit, the gate adds no trailer, so git stops it.

The release check: before it adds the trailer, the commit-msg hook runs `just release-check` with the path of the
message file in `JN_RELEASE_MESSAGE`. `just check` ran before the message was written, so it could not count it. With
the message, `release_tag.py --check` counts it for the next tag, and fails when the type of the commit, such as
`fix:`, asks for a release that the release script cannot write into the manifest. For an amend, it sets `JN_RELEASE_AMEND=1`, so the new message replaces the
message of HEAD, but only when `--amend` comes before any text of the message in the command that ps shows. A word
`--amend` after the text sets `JN_RELEASE_AMEND=maybe`, and HEAD counts too. It puts
the option `--cleanup` of git in `JN_RELEASE_CLEANUP`, or `unknown` when ps cannot tell it, and sets
`JN_RELEASE_EDITOR=1` when the options show that git runs the editor, or `unknown` when an option after the text
can hide it, so the check cleans up the message as git
does. The hook skips the check for a merge and for an amend of a merge, since the release skips merge
commits, during a rebase, and when the Justfile has no recipe `release-check`. The check stops the commit when it runs longer than
120 seconds.

`--trailers BASE HEAD` is the check of CI, which `just ci-gate` runs. `ci-gate` is a step of `just check` too, so CI
checks only a part of `just check`. With no BASE and HEAD, it reads them from CI, from the pre-push hook, or from
the base branch on origin, as `ci_range` says. Each commit in BASE..HEAD must have one trailer of the gate, with one
word, `patch:<id>`, and the ID must be the patch ID of the commit. Three kinds of commit
are exempt, and the check names each one it skips: a merge with no change of its own, as git merge-tree makes it, a
commit whose author is a GitHub bot, and a commit from before the gate, when no commit it reaches changed
`.agents/stack.json`. Another merge needs one trailer `tree:<tree>` with its own tree. CI runs no other step of `just check`
again: the trailer says that the gate saw a pass of it. The trailer is a claim of the gate, not a proof: an agent
could write one by hand, and the review of the pull request is the check of that.

Usage: commit_gate.py [--hook pre-commit|pre-merge-commit|commit-msg] [MESSAGE_FILE], or commit_gate.py --trailers
[BASE HEAD], or commit_gate.py --check-hooks. It exits with 0 to let the commit through and with 1 to stop it.

`commit_gate.py --check-hooks` checks that the pre-commit framework runs the hooks of the tasker role: pre-commit,
pre-merge-commit and commit-msg, which run the gate, and pre-push, which runs pre_push.py, or just ci in an older
config. It exits with 0 when the hook of
each stage is a hook of pre-commit for .pre-commit-config.yaml whose Python has pre-commit, and the config has the
hooks of the role, and with 1 when not. The tasker role runs it as the check of its hook install.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

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
# The page rule of the nossaifd role. With it, @pages is the changed files that its is_page accepts.
PAGE_RULE = ".agents/skills/nossaifd/scripts/prose_gate.py"

# The API rule of a language profile, by its name in the key `profiles` of stack.json. With it, @api is the changed
# files that its is_api accepts.
API_RULE = ".agents/just/{}/api_rule.py"

STACK = ".agents/stack.json"
REQUIRED = ".agents/targets/required.txt"
GENERATED = ".agents/generated.txt"
RUN_LOG = "just.jsonl"
# The folder of a log folder where agentic_target.py keeps the trees of the packets and the records.
TREES = "objects"


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


def git_process() -> Tuple[Optional[int], List[str]]:
    """The process ID and the argv of the nearest git above this process, from ps, or (None, []) when ps cannot
    tell. A hook manager such as pre-commit can stand between git and the gate."""
    pid = os.getppid()
    for _ in range(6):
        run = subprocess.run(["ps", "-o", "ppid=", "-o", "args=", "-p", str(pid)], stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, errors="replace")
        fields = run.stdout.split()
        if run.returncode != 0 or len(fields) < 2:
            return None, []
        if os.path.basename(fields[1]) == "git":
            return pid, fields[1:]
        pid = int(fields[0])
    return None, []


def git_argv() -> List[str]:
    """The argv of the nearest git above this process, from ps, or [] when ps cannot tell. Ps joins the words of
    each argument with spaces."""
    return git_process()[1]


def macos_argv(pid: int) -> Optional[List[str]]:
    """The argv of process PID, one entry for each argument, from the sysctl KERN_PROCARGS2 of macOS, or None. The
    data is argc as 4 bytes, the path of the program, padding of NUL bytes, then each argument with a NUL after it."""
    try:
        import ctypes
        import ctypes.util

        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        mib = (ctypes.c_int * 3)(1, 49, pid)  # CTL_KERN, KERN_PROCARGS2
        size = ctypes.c_size_t(0)
        if libc.sysctl(mib, 3, None, ctypes.byref(size), None, ctypes.c_size_t(0)) != 0 or size.value < 4:
            return None
        buffer = ctypes.create_string_buffer(size.value)
        if libc.sysctl(mib, 3, buffer, ctypes.byref(size), None, ctypes.c_size_t(0)) != 0:
            return None
    except (OSError, AttributeError, TypeError):
        return None
    data = buffer.raw[:size.value]
    count = int.from_bytes(data[:4], sys.byteorder)
    rest = data[4:]
    end = rest.find(b"\0")
    if end < 0:
        return None
    rest = rest[end:].lstrip(b"\0")
    words = rest.split(b"\0")
    if count < 1 or len(words) < count:
        return None
    return [word.decode(errors="replace") for word in words[:count]]


def exact_git_argv() -> Optional[List[str]]:
    """The argv of the nearest git above this process, one entry for each argument, from /proc on Linux or from the
    sysctl of macOS, or None when neither can tell."""
    pid, _ = git_process()
    if pid is None:
        return None
    try:
        data = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return macos_argv(pid) if sys.platform == "darwin" else None
    return [word.decode(errors="replace") for word in data.split(b"\0")[:-1]] or None


def exact_options(argv: Sequence[str]) -> Dict[str, object]:
    """The options of `git commit` in an exact argv, where the value of an option such as -m is one entry: amend,
    editor (True when git runs the editor, None when the options do not say), gives (an option that gives the
    message), cleanup (the mode, or None), allow_empty (--allow-empty-message), template (the value of -t, or None)
    and verbose (-v)."""
    found: Dict[str, object] = {"amend": False, "editor": None, "gives": False, "cleanup": None,
                                "allow_empty": False, "template": None, "verbose": False}
    if "commit" not in argv:
        return found
    words = list(argv[argv.index("commit") + 1:])
    reedit = False
    index = 0

    def long(name: str, option: str, least: int = 3) -> bool:
        return len(name) >= least and option.startswith(name)

    def value(equals: str, rest: str) -> str:
        nonlocal index
        if equals:
            return rest
        index += 1
        return words[index - 1] if index - 1 < len(words) else ""

    while index < len(words):
        word = words[index]
        index += 1
        if word == "--":
            break
        if not word.startswith("-") or word == "-":
            continue
        if word.startswith("--"):
            name, equals, rest = word.partition("=")
            if long(name, "--amend", 4):
                found["amend"] = True
            elif long(name, "--no-amend", 6):
                found["amend"] = False
            elif long(name, "--allow-empty-message", len("--allow-empty-m")):
                found["allow_empty"] = True
            elif name == "--edit" or (long(name, "--edit", 4) and name != "--e"):
                found["editor"] = True
            elif long(name, "--no-edit", 6):
                found["editor"] = False
            elif long(name, "--verbose", 4):
                found["verbose"] = True
            elif long(name, "--no-verbose", 6):
                found["verbose"] = False
            elif long(name, "--no-cleanup", 6):
                found["cleanup"] = "default"
            elif long(name, "--cleanup"):
                found["cleanup"] = value(equals, rest)
            elif long(name, "--template"):
                found["template"] = value(equals, rest)
            elif any(long(name, option) for option in TEXT_OPTIONS):
                if any(long(name, option) for option in ("--message", "--file", "--reuse-message")):
                    found["gives"] = True
                if long(name, "--reedit-message"):
                    found["gives"] = reedit = True
                value(equals, rest)
            continue
        for at, letter in enumerate(word[1:], start=1):
            if letter in "Su":
                break  # -S and -u take their value in the same word only.
            if letter == "e":
                found["editor"] = True
            if letter == "v":
                found["verbose"] = True
            if letter in TEXT_SHORT:
                found["gives"] = found["gives"] or letter in "mFCc"
                reedit = reedit or letter == "c"
                # The value is the rest of the word, or the next word when the letter ends the word.
                given = word[at + 1:] if at < len(word) - 1 else (words[index] if index < len(words) else "")
                index += 1 if at == len(word) - 1 else 0
                if letter == "t":
                    found["template"] = given
                break
    if found["editor"] is None:
        found["editor"] = reedit or not found["gives"]
    return found


def amend_in_exact(argv: Sequence[str]) -> bool:
    """True when the exact argv of `git commit` has the option --amend, or an abbreviation of it. The value of an
    option such as -m is one entry, so a word --amend in the message does not count."""
    return bool(exact_options(argv)["amend"])


def is_amend(argv: Sequence[str]) -> bool:
    """True for `git commit --amend`, also with an abbreviation of the option that git accepts, such as `--am`. A
    message can hold the same word, so the gate then applies the rules of both possible parents."""
    return any(len(word) >= 4 and "--amend".startswith(word) for word in argv)


# The long options of git commit whose value can be text with spaces, so that ps shows its words as more words.
TEXT_OPTIONS = ("--message", "--file", "--reuse-message", "--reedit-message", "--template", "--author", "--date",
                "--trailer", "--fixup", "--squash", "--pathspec-from-file")
# The short options of git commit that take a value: -m, -F, -C, -c and -t.
TEXT_SHORT = "mFCct"


def option_words(argv: Sequence[str]) -> Tuple[List[str], bool]:
    """The options of `git commit` in ARGV up to the first word that may be text, such as the value of -m, and True
    when no such word follows. Ps joins the words of each argument with spaces, so a message such as "docs: drop
    --amend" gives the word --amend, which only the words before the message can tell apart."""
    if "commit" not in argv:
        return [], False
    words = list(argv[argv.index("commit") + 1:])
    sure = []
    index = 0
    while index < len(words):
        word = words[index]
        if not word.startswith("-") or word == "--":
            return sure, False
        name = word.partition("=")[0]
        if word.startswith("--"):
            if len(name) >= 3 and any(option.startswith(name) for option in TEXT_OPTIONS):
                return sure, False
            sure.append(word)
            if len(name) >= 3 and "--cleanup".startswith(name) and "=" not in word:
                if index + 1 < len(words):
                    sure.append(words[index + 1])
                index += 1
        elif any(letter in TEXT_SHORT for letter in word[1:]):
            return sure, False
        else:
            sure.append(word)
        index += 1
    return sure, True


def is_sure_amend(argv: Sequence[str]) -> bool:
    """True when an option before any text of the command is --amend, so the commit is an amend."""
    return is_amend(option_words(argv)[0])


def cleanup_of(argv: Sequence[str]) -> Optional[str]:
    """The value of the option --cleanup of git, also abbreviated as git accepts, such as `--cl=strip`. None when the
    command has no such option, and `unknown` when ps cannot tell the command, or when a word that may be text of the
    message looks like the option."""
    if not argv:
        return "unknown"
    sure, complete = option_words(argv)

    def values(words: Sequence[str]) -> List[str]:
        found = []
        for index, word in enumerate(words):
            name, equals, value = word.partition("=")
            negated = name.startswith("--no-")
            bare = "--" + name[len("--no-"):] if negated else name
            if len(bare) < 3 or not "--cleanup".startswith(bare):
                continue
            if negated:
                found.append("default")
            elif equals:
                found.append(value)
            else:
                found.append(words[index + 1] if index + 1 < len(words) else "")
        return found

    if "commit" not in argv or (not complete and values(argv[argv.index("commit") + 1 + len(sure):])):
        return "unknown"
    given = values(sure)
    return given[-1] if given else None


def runs_editor(argv: Sequence[str]) -> bool:
    """True when the options before any text of the command show that git runs the editor: -e or --edit, or no
    option that gives the message."""
    sure, complete = option_words(argv)
    def short_letters(word: str) -> str:
        # -S and -u take a value in the same word, such as -Skey, so the letters after them are no options.
        letters = word[1:] if word.startswith("-") and not word.startswith("--") else ""
        return re.split("[Su]", letters)[0]

    if any(word == "--edit" or "e" in short_letters(word) for word in sure):
        return True
    gives = ("--no-edit", "--no-e", "--no-ed", "--no-edi")
    return complete and bool(argv) and not any(word.startswith(gives) for word in sure)


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


# The script that loads a rule from the file in argv[1], in a Python of its own, and prints each path of standard
# input that its function argv[2] accepts: is_page for the page rule, is_api for an API rule. The paths come and go
# with a NUL after each one, and the last word is PAGES_END, so that a rule that ends its Python early cannot give "no
# path". A path that is not UTF-8 keeps its bytes, as git() keeps them. Exit 3 with NO_FUNCTION as the last line of
# standard error: no such function. The rule itself can exit with 3, and then it fails.
# No changed path is "/", so the last word cannot be a path.
PAGES_END = "/"
NO_FUNCTION = "commit-gate: the rule has no such function"
# The seconds that a rule can take for the paths of one commit.
RULE_TIMEOUT = 120
RULE_OF = """import importlib.util, sys
spec = importlib.util.spec_from_file_location("commit_gate_rule", sys.argv[1])
module = importlib.util.module_from_spec(spec)
out = sys.stdout.buffer
# What the rule prints goes to standard error, so that it cannot come after the end word.
sys.stdout = sys.stderr
spec.loader.exec_module(module)
rule = getattr(module, sys.argv[2], None)
if not callable(rule):
    sys.stderr.write("\\n%s\\n")
    sys.stderr.flush()
    sys.exit(3)
for path in sys.stdin.buffer.read().decode(errors="surrogateescape").split("\\0"):
    if path and rule(path):
        out.write(path.encode(errors="surrogateescape") + b"\\0")
out.write(b"%s\\0")
out.flush()""" % (NO_FUNCTION, PAGES_END)


def rule_runner(root: Path, text: str, name: str, function: str, what: str) -> Callable[[List[str]], List[str]]:
    """The paths of a list that FUNCTION of the rule TEXT accepts. NAME is the path of the rule, and WHAT names the
    rule in a message, such as "the page rule". The rule runs in a Python of its own, so it can only answer which
    paths it accepts: it cannot end the gate or change its environment."""

    def accepted(paths: List[str]) -> List[str]:
        with tempfile.TemporaryDirectory(prefix="commit-gate-rule-") as away:
            script = Path(away) / "rule.py"
            script.write_text(text, errors="surrogateescape")
            try:
                run = subprocess.run([sys.executable, "-I", "-B", "-c", RULE_OF, str(script), function], cwd=root,
                                     input="".join(f"{path}\0" for path in paths).encode(errors="surrogateescape"),
                                     capture_output=True, timeout=RULE_TIMEOUT)
            except subprocess.TimeoutExpired:
                raise Stop(f"{what} {name} of the parent does not finish in {RULE_TIMEOUT} seconds: run "
                           "`just install`")
        python = f"Python {sys.version.split()[0]}"
        error = run.stderr.decode(errors="replace").strip().splitlines()[-1:] or ["no message"]
        if run.returncode == 3 and error == [NO_FUNCTION]:
            raise Stop(f"{what} {name} of the parent has no {function}: run `just install`")
        if run.returncode != 0:
            raise Stop(f"{what} {name} of the parent fails in {python} ({error[0]}): run "
                       "`just install`, or run the gate with a Python that the rule supports")
        found = [path for path in run.stdout.decode(errors="surrogateescape").split("\0") if path]
        if found[-1:] != [PAGES_END]:
            raise Stop(f"{what} {name} of the parent ends before it checks each path: run `just install`")
        found = found[:-1]
        if not set(found) <= set(paths):
            raise Stop(f"{what} {name} of the parent names paths that the commit does not change")
        return found

    return accepted


def page_rule(root: Path, parent: Optional[str]) -> Optional[Callable[[List[str]], List[str]]]:
    """The pages of a list of paths, by is_page of the nossaifd role, from its prose_gate.py in PARENT. None without
    the role, and on the first commit, where the globs apply as the default required.txt does. The rule comes from
    the parent, so a change cannot loosen the rule for its own pages."""
    text = None if parent is None else read_at(root, parent, PAGE_RULE)
    if text is None:
        return None
    return rule_runner(root, text, PAGE_RULE, "is_page", "the page rule")


def profile_names(stack: object) -> List[str]:
    """The names of the key `profiles` of a stack.json. A name with a `/`, or `.` or `..`, names no folder of
    .agents/just/, so it has no rule."""
    names = stack.get("profiles") if isinstance(stack, dict) else None
    if not isinstance(names, list):
        return []
    return [name for name in names if isinstance(name, str) and name not in ("", ".", "..")
            and all(c.isalnum() or c in "-_." for c in name)]


def api_rules(root: Path, parent: Optional[str], stack: dict,
              parent_text: Optional[str]) -> List[Callable[[List[str]], List[str]]]:
    """The API rules of the profiles of the parent and of the commit, each from its api_rule.py in PARENT, so a
    change cannot loosen the rule for its own API. A profile whose parent has no rule gives none, and the first
    commit has none."""
    if parent is None:
        return []
    try:
        parent_stack = json.loads(parent_text) if parent_text is not None else None
    except ValueError:
        parent_stack = None
    rules = []
    for name in dict.fromkeys(profile_names(parent_stack) + profile_names(stack)):
        path = API_RULE.format(name)
        text = read_at(root, parent, path)
        if text is not None:
            rules.append(rule_runner(root, text, path, "is_api", "the API rule"))
    return rules


def changed_files(root: Path, parent: Optional[str], tree: str, generated: List[str]) -> List[str]:
    """The paths that the commit changes, less the paths of generated.txt. A deleted path counts."""
    env = plain_env()
    before = parent or git(["hash-object", "-t", "tree", "--stdin"], root, env).strip()
    specs = [":(glob)**", *[f":(exclude,glob){g}" for g in generated]]
    out = git(["diff", "--name-only", "-z", "--no-renames", before, tree, "--", *specs], root, env)
    return [path for path in out.split("\0") if path]


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


def refusal_notes(folders: List[Path], missing: List[str], tree: str, root: Path) -> List[str]:
    """Why each missing target has no record, from the refusal files that the record hook wrote: the latest refusal
    of each target, with its nonce and reason. A refusal counts here when its input tree is TREE, or, for a target
    that changes files, when its packet is of this worktree. A record of the same target and input tree that is newer
    than the refusal, whatever its status, or a record with the nonce of the refusal, makes the refusal old news. A
    record of another tree, as from another worktree, does not. A refusal of a target that changes files, which counts
    by its worktree, is also old news after a newer record of that target from the same worktree. The worktree of a
    record is in the packet of its nonce. A file that the gate cannot read is
    left out, so a bad refusal file never stops the gate with a fault of its own."""
    newest_record: Dict[Tuple[str, str], float] = {}
    # The newest record of each target that changes files, by the worktree of its packet.
    newest_changer: Dict[Tuple[str, str], float] = {}
    record_nonces: Set[str] = set()
    for folder in folders:
        for path in (folder / "records").glob("*.json") if (folder / "records").is_dir() else []:
            try:
                record, when = json.loads(path.read_text()), path.stat().st_mtime
                record_nonces.add(path.stem)
                if (isinstance(record, dict) and record.get("version") == 1 and isinstance(record.get("target"), str)
                        and isinstance(record.get("status"), str) and is_tree(record.get("input_tree"))):
                    key = (record["target"], record["input_tree"])
                    newest_record[key] = max(when, newest_record.get(key, 0.0))
                    if record["target"] in CHANGERS and isinstance(record.get("nonce"), str):
                        packet = json.loads((folder / "packets" / f"{path.stem}.json").read_text())
                        if isinstance(packet, dict) and isinstance(packet.get("worktree"), str):
                            place = (record["target"], str(Path(packet["worktree"]).resolve()))
                            newest_changer[place] = max(when, newest_changer.get(place, 0.0))
            except Exception:
                continue
    latest: Dict[str, Tuple[float, dict]] = {}
    for folder in folders:
        for path in (folder / "refusals").glob("*.json") if (folder / "refusals").is_dir() else []:
            try:
                refusal, when = json.loads(path.read_text()), path.stat().st_mtime
                if not (isinstance(refusal, dict) and refusal.get("version") == 1
                        and isinstance(refusal.get("target"), str) and refusal["target"] in missing
                        and isinstance(refusal.get("nonce"), str) and isinstance(refusal.get("reason"), str)):
                    continue
                target = refusal["target"]
                key = (target, refusal.get("input_tree"))
                if refusal["nonce"] in record_nonces or newest_record.get(key, -1.0) >= when:  # type: ignore[arg-type]
                    continue
                if refusal.get("input_tree") != tree:
                    worktree = refusal.get("worktree")
                    if target not in CHANGERS or not isinstance(worktree, str):
                        continue
                    if Path(worktree).resolve() != root.resolve():
                        continue
                    if newest_changer.get((target, str(root.resolve())), -1.0) >= when:
                        continue
                if target not in latest or when > latest[target][0]:
                    latest[target] = (when, refusal)
            except Exception:
                continue
    notes = []
    for target in missing:
        if target in latest:
            refusal = latest[target][1]
            # The reason comes from the fresh agent, so it loses each control character.
            reason = "".join(c if c.isprintable() else " " for c in refusal["reason"]).strip()[:600]
            nonce = "".join(c for c in refusal["nonce"] if c.isalnum())[:64]
            notes.append(f"The record hook refused the result of `just {target}` with the nonce {nonce}: {reason}")
    return notes


# The scope of each record: the kinds of path whose change after the record voids it. A record of tree T1 counts for
# the commit tree T2 when no path that differs between T1 and T2 is of a kind in its scope. The kinds come from
# path_kind. "code" is in every scope, since it holds each path whose kind is in doubt. A target with no entry here,
# such as a target of the project, has every kind in its scope.
#
# - review and test-review read the code, the tests and the data, and not the pages, so a change of a page alone
#   keeps them.
# - prose works on the pages and on the docstrings and comments of the code, so a change of the code voids it. A
#   change of data alone, such as a lock file, keeps it.
# - update-docs checks that the docs match the code, so every change voids it.
PAGE, CODE, DATA = "page", "code", "data"
SCOPES: Dict[str, Set[str]] = {
    "review": {CODE, DATA},
    "test-review": {CODE, DATA},
    "prose": {PAGE, CODE},
    "update-docs": {PAGE, CODE, DATA},
}
ALL_KINDS = {PAGE, CODE, DATA}
# A page is a Markdown file under docs/. A Markdown file at the top, such as README.md, is code: a build can put it in
# the docs of a crate or a package, and run its examples as tests. These names are instructions for agents, legal text
# or files that tools read, so they are code under docs/ too. The match is on the start of the name, in any case.
NOT_PAGES = ("AGENTS", "CLAUDE", "GEMINI", "SKILL", "CHANGELOG", "LICENSE", "COPYING", "SECURITY", "CODEOWNERS")
# The suffixes of data files: files that hold no prose for a person and no docstring.
DATA_SUFFIXES = (".json", ".jsonl", ".lock", ".csv", ".tsv", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
                 ".pdf", ".woff", ".woff2", ".ttf", ".otf", ".zip", ".gz", ".tgz")
# The git mode of a plain file, and of no file, as the side of an added or a deleted path shows it. An executable
# file is code.
REGULAR_MODES = ("100644", "000000")


def scope_of(target: str) -> Set[str]:
    return SCOPES.get(target, ALL_KINDS)


def path_kind(path: str, modes: Sequence[str], code: Sequence[str] = (), linked: bool = False) -> str:
    """The kind of a changed path: PAGE, DATA or CODE. MODES are the git modes of the path on the two sides. CODE
    holds the code globs of the project, from the keys `code` and `tests` of stack.json: a path that one matches is
    code, such as a page that the tests run. LINKED is True when either tree holds a link, so a page can be the text
    of another path. A path whose kind is in doubt is CODE: a link, a submodule, an executable file,
    a Markdown file outside docs/, a name in NOT_PAGES, or any path when LINKED holds."""
    if any(mode not in REGULAR_MODES for mode in modes) or any(glob_match(glob, path) for glob in code):
        return CODE
    parts = path.split("/")
    name = parts[-1]
    if any(not part or part.startswith((".", "_")) for part in parts):
        return CODE
    if (name.endswith(".md") and len(parts) > 1 and parts[0] == "docs" and not name.upper().startswith(NOT_PAGES)
            and not linked):
        return PAGE
    if name.endswith(DATA_SUFFIXES):
        return DATA
    return CODE


def glob_match(glob: str, path: str) -> bool:
    """True when the git glob GLOB, as `:(glob)` reads it, may match PATH or a folder above it, as a pathspec of git
    matches each path in a folder that it names. A leading `./`, a `..` and an ending `/` go first. A class such as
    `[ab]` matches any one character, so the match is never narrower than the match of git."""
    glob = posixpath.normpath(glob).lstrip("/") if glob not in ("", ".") else "**"
    if glob in (".", "") or glob.startswith(".."):
        return True
    pattern = glob_regex(glob)
    parts = path.split("/")
    return any(re.fullmatch(pattern, "/".join(parts[:end]), re.DOTALL) for end in range(1, len(parts) + 1))


def glob_regex(glob: str) -> str:
    out, index = "", 0
    while index < len(glob):
        if glob.startswith("**/", index):
            out, index = out + "(?:.*/)?", index + 3
        elif glob.startswith("**", index):
            out, index = out + ".*", index + 2
        elif glob[index] == "*":
            out, index = out + "[^/]*", index + 1
        elif glob[index] == "?":
            out, index = out + "[^/]", index + 1
        elif glob[index] == "[" and "]" in glob[index + 2 + (glob[index + 1:index + 2] in ("!", "^")):]:
            # A `]` right after `[` or `[!` is a character of the class.
            out, index = out + "[^/]", glob.index("]", index + 2 + (glob[index + 1:index + 2] in ("!", "^"))) + 1
        else:
            out, index = out + re.escape(glob[index]), index + 1
    return out


# The mode of a tree, of a link and of a submodule in a tree object, as git writes it.
TREE_MODE, LINK_MODE, SUBMODULE_MODE = "040000", "120000", "160000"


class Objects:
    """The tree and link objects of the gate, read by their IDs. Each object comes from the folder `objects` of a log
    folder, where agentic_target.py keeps it, or from git with no replace refs, and each must hash to its ID. So
    neither `git replace` nor a forged object file can change what the gate compares. None stands for an object
    that no place has, or whose content does not match its ID."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.kept = [folder / TREES for folder in log_folders(root)]
        name = git(["rev-parse", "--show-object-format"], root, plain_env(), check=False).strip() or "sha1"
        self.hash = name if name in ("sha1", "sha256") else "sha1"
        self.size = 20 if self.hash == "sha1" else 32
        self.cache: Dict[Tuple[str, str], Optional[bytes]] = {}
        self.linked: Dict[str, bool] = {}
        self.process: Optional[subprocess.Popen] = None

    def close(self) -> None:
        if self.process is not None:
            self.process.stdin.close()
            self.process.wait()
            self.process.stdout.close()
            self.process = None

    def matches(self, oid: str, kind: str, data: bytes) -> bool:
        return hashlib.new(self.hash, b"%s %d\0" % (kind.encode(), len(data)) + data).hexdigest() == oid

    def read(self, oid: str, kind: str) -> Optional[bytes]:
        if (oid, kind) in self.cache:
            return self.cache[(oid, kind)]
        data = None
        if is_tree(oid):
            for folder in self.kept:
                try:
                    found = (folder / oid).read_bytes()
                except OSError:
                    continue
                if self.matches(oid, kind, found):
                    data = found
                    break
            if data is None:
                found = self.from_git(oid, kind)
                data = found if found is not None and self.matches(oid, kind, found) else None
        self.cache[(oid, kind)] = data
        return data

    def from_git(self, oid: str, kind: str) -> Optional[bytes]:
        if self.process is None:
            env = dict(plain_env(), GIT_NO_REPLACE_OBJECTS="1")
            self.process = subprocess.Popen(["git", "--no-replace-objects", "cat-file", "--batch"], cwd=self.root,
                                            env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.DEVNULL)
        self.process.stdin.write(oid.encode() + b"\n")
        self.process.stdin.flush()
        header = self.process.stdout.readline().split()
        if len(header) != 3 or header[0].decode() != oid:
            return None
        data = self.process.stdout.read(int(header[2]))
        self.process.stdout.read(1)
        return data if header[1].decode() == kind else None

    def entries(self, oid: str) -> Optional[Dict[str, Tuple[str, str]]]:
        """The entries of the tree OID, by name, as their modes and IDs."""
        data = self.read(oid, "tree")
        if data is None:
            return None
        found: Dict[str, Tuple[str, str]] = {}
        index = 0
        while index < len(data):
            space = data.find(b" ", index)
            nul = data.find(b"\0", space + 1)
            if space < 0 or nul < 0 or nul + 1 + self.size > len(data):
                return None
            mode = data[index:space].decode(errors="replace").zfill(6)
            name = data[space + 1:nul].decode(errors="surrogateescape")
            found[name] = (mode, data[nul + 1:nul + 1 + self.size].hex())
            index = nul + 1 + self.size
        return found

    def leaves(self, oid: str, prefix: str) -> Optional[List[Tuple[str, str]]]:
        """Each path below the tree OID, with its mode, under PREFIX."""
        entries = self.entries(oid)
        if entries is None:
            return None
        out: List[Tuple[str, str]] = []
        for name, (mode, child) in entries.items():
            if mode == TREE_MODE:
                below = self.leaves(child, f"{prefix}{name}/")
                if below is None:
                    return None
                out += below
            else:
                out.append((f"{prefix}{name}", mode))
        return out

    def changes(self, before: str, after: str, prefix: str = "") -> Optional[List[Tuple[str, Tuple[str, str]]]]:
        """Each path that differs between the trees BEFORE and AFTER, with its mode on each side, or 000000 on the
        side that lacks it. A rename is a deletion and an addition, and a change of a file to a folder gives both."""
        if before == after:
            return []
        old, new = self.entries(before), self.entries(after)
        if old is None or new is None:
            return None
        out: List[Tuple[str, Tuple[str, str]]] = []
        for name in sorted(set(old) | set(new)):
            one, two = old.get(name), new.get(name)
            if one == two:
                continue
            path = prefix + name
            if one and two and one[0] == two[0] == TREE_MODE:
                below = self.changes(one[1], two[1], f"{path}/")
                if below is None:
                    return None
                out += below
                continue
            sides = []
            for side, entry in ((0, one), (1, two)):
                if entry and entry[0] == TREE_MODE:
                    below = self.leaves(entry[1], f"{path}/")
                    if below is None:
                        return None
                    out += [(leaf, (mode, "000000") if side == 0 else ("000000", mode)) for leaf, mode in below]
                    sides.append("000000")
                else:
                    sides.append(entry[0] if entry else "000000")
            if sides != ["000000", "000000"]:
                out.append((path, (sides[0], sides[1])))
        return out

    def has_links(self, oid: str) -> Optional[bool]:
        """True when the tree OID holds a link at any depth. A link can make a page the text of another path, also
        through `..` and folders that are links, or a name in another case on a file system that ignores case."""
        if oid in self.linked:
            return self.linked[oid]
        entries = self.entries(oid)
        if entries is None:
            return None
        found = False
        for mode, child in entries.values():
            if mode == LINK_MODE:
                found = True
            elif mode == TREE_MODE:
                below = self.has_links(child)
                if below is None:
                    return None
                found = found or below
            if found:
                break
        self.linked[oid] = found
        return found


def changed_kinds(objects: "Objects", before: str, after: str, code: Sequence[str] = ()) -> Optional[Set[str]]:
    """The kinds of the paths that differ between the trees BEFORE and AFTER, or None when the gate cannot compare
    them, as for a tree that neither git nor a log folder has. A record from before agentic_target.py kept its trees
    counts for its own tree only. Each side of a rename counts, and a deleted path counts. CODE is as in path_kind."""
    if before == after:
        return set()
    changes = objects.changes(before, after)
    if changes is None:
        return None
    kinds = {path_kind(path, modes, code) for path, modes in changes}
    if PAGE not in kinds:
        return kinds
    # A link of either tree can make a page the text of another path, so then each page is code.
    linked = [objects.has_links(tree) for tree in (before, after)]
    if None in linked:
        return None
    return {path_kind(path, modes, code, any(linked)) for path, modes in changes}


def scope_code(root: Path, parents: Sequence[Optional[str]], stack: dict) -> List[str]:
    """The globs of the keys `code` and `tests` of the stack.json of the commit and of each parent, for path_kind. A
    path that a profile names as code or tests is code, though it looks like a page."""
    stacks: List[object] = [stack]
    for parent in parents:
        text = None if parent is None else read_at(root, parent, STACK)
        try:
            stacks.append(json.loads(text) if text is not None else None)
        except ValueError:
            continue
    globs: List[str] = []
    for one in stacks:
        globs += code_globs(one)
        tests = one.get("tests") if isinstance(one, dict) else None
        if isinstance(tests, dict):
            globs += [g for found in tests.values() if isinstance(found, list) for g in found if isinstance(g, str) and g]
    return list(dict.fromkeys(globs))


def missing_targets(required: List[str], records: List[dict], tree: str, root: Optional[Path] = None,
                    code: Sequence[str] = ()) -> List[str]:
    """The required targets with no record that counts for TREE, in the order to run them.

    A record of a target that changes no file counts when its input tree is its output tree, and no path that differs
    between that tree and TREE is in the scope of the target. A record of a target that changes files, such as
    update-docs, counts when the same holds for its output tree. Between its output tree and TREE, the records of the
    targets after it in CHANGERS may come, since they change only what they check: update-docs, then prose. A skip
    counts for its own tree only. Without ROOT, the gate cannot compare trees, and a record counts for its own tree
    only. CODE is the code globs of the project, as path_kind reads them."""
    cache: Dict[Tuple[str, str], Optional[Set[str]]] = {}
    objects = Objects(root) if root is not None else None
    try:
        return _missing(required, records, tree, objects, code, cache)
    finally:
        if objects is not None:
            objects.close()


def _missing(required: List[str], records: List[dict], tree: str, objects: Optional["Objects"], code: Sequence[str],
             cache: Dict[Tuple[str, str], Optional[Set[str]]]) -> List[str]:

    def clean(before: str, after: str, scope: Set[str]) -> bool:
        """True when no path that differs between BEFORE and AFTER is in SCOPE."""
        if before == after:
            return True
        # With every kind in the scope, any change voids the record, so only the same tree counts.
        if objects is None or scope >= ALL_KINDS:
            return False
        if (before, after) not in cache:
            cache[(before, after)] = changed_kinds(objects, before, after, code)
        kinds = cache[(before, after)]
        return kinds is not None and not kinds & scope

    def own(record: dict) -> Optional[str]:
        """The tree that the record checked last, or None for a record that cannot count."""
        if record.get("source") == "skip":
            return record["output_tree"] if record["input_tree"] == tree == record["output_tree"] else None
        if record["target"] not in CHANGERS and record["input_tree"] != record["output_tree"]:
            return None
        return record["output_tree"]

    by_target: Dict[str, List[dict]] = {}
    for record in records:
        by_target.setdefault(record["target"], []).append(record)

    def reaches(start: str, scope: Set[str], later: Sequence[str]) -> bool:
        """True when TREE comes from START with no change in SCOPE, other than the changes of the records of the
        targets in LATER, in their order."""
        if clean(start, tree, scope):
            return True
        for index, target in enumerate(later):
            for record in by_target.get(target, []):
                if record.get("source") != "skip" and clean(start, record["input_tree"], scope) \
                        and reaches(record["output_tree"], scope, later[index + 1:]):
                    return True
        return False

    def counts(target: str) -> bool:
        scope = scope_of(target)
        later = CHANGERS[CHANGERS.index(target) + 1:] if target in CHANGERS else ()
        # A record of TREE itself needs no git, so those come first.
        for record in sorted(by_target.get(target, []), key=lambda record: own(record) != tree):
            start = own(record)
            if start is not None and reaches(start, scope, later):
                return True
        return False

    changers = [t for t in CHANGERS if t in required and not counts(t)]
    return changers + [t for t in required if t not in CHANGERS and not counts(t)]


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
    parent_stack = None if parent is None else read_at(root, parent, STACK)
    code = merged_code(stack, parent_stack)
    # Each alias that rules decide, and its rules. @pages without its rule keeps its globs, and @api without a rule
    # names no file, as pathspecs() says.
    aliases: Dict[str, List[Callable[[List[str]], List[str]]]] = {}
    if any("@pages" in paths for paths in required_paths.values()):
        rule = page_rule(root, parent)
        if rule is not None:
            aliases["@pages"] = [rule]
    if any("@api" in paths for paths in required_paths.values()):
        aliases["@api"] = api_rules(root, parent, stack, parent_stack)
    answers: Dict[str, bool] = {}
    changed: List[List[str]] = []

    def matches(alias: str) -> bool:
        if alias not in answers:
            if not changed:
                changed.append(changed_files(root, parent, tree, generated))
            # Each rule runs, so a broken rule stops the commit though another rule accepts a path.
            answers[alias] = any([bool(rule(changed[0])) for rule in aliases[alias]])
        return answers[alias]

    def needed(paths: List[str]) -> bool:
        # Each rule runs before any answer, so a broken rule stops the commit though another alias matches.
        for alias in aliases:
            matches(alias)
        for alias in aliases:
            if alias in paths:
                if matches(alias):
                    return True
                paths = [path for path in paths if path != alias]
        return changes_match(root, parent, tree, pathspecs(paths, code, generated))

    return [t for t, paths in required_paths.items() if needed(paths)]


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
                   "put the rest aside: run `git stash --keep-index -u`, then the targets that the new tree needs and "
                   "`just check`, then commit, then `git stash pop`")

    folders = log_folders(root)
    if not has_pass(folders, tree, stack["steps"]):
        message = "no pass of `just check` for this tree: run `just check`"
        if os.environ.get("PRE_COMMIT") == "1":
            # The framework puts the unstaged changes aside before its hooks, so partial staging looks like this.
            message += (". If only part of the changes is staged, pre-commit put the rest aside, so a pass of the "
                        "whole worktree does not count. Stage them all, or run `git stash --keep-index -u`, then the "
                        "targets that the new tree needs and `just check`, then commit, then `git stash pop`")
        raise Stop(message)

    if is_agent():
        missing = missing_targets(required, load_records(folders), tree, root, scope_code(root, parents, stack))
        if missing:
            notes = refusal_notes(folders, missing, tree, root)
            raise Stop("no record for this tree of " + ", ".join(f"`just {t}`" for t in missing)
                       + ": run them in this order" + "".join(f". {note}" for note in notes))


TRAILER = "Commit-Gate"


def empty_tree(root: Path) -> str:
    return git(["mktree"], root, plain_env()).strip()


def patch_id(diff: str, root: Path) -> str:
    """The stable patch ID of DIFF, or `none` for a change with no diff, as in git commit --allow-empty."""
    run = subprocess.run(["git", "patch-id", "--verbatim"], cwd=root, input=diff, capture_output=True, text=True,
                         errors="surrogateescape")
    fields = run.stdout.split()
    return fields[0] if run.returncode == 0 and fields else "none"


# No lines of context, so a change of the lines next to a change, as in a rebase, keeps the patch ID.
DIFF_OPTIONS = ["-p", "-U0", "--no-renames", "--binary", "--no-color", "--no-ext-diff"]


def staged_patch_id(root: Path, parent: Optional[str]) -> str:
    """The patch ID of the commit that git is making: the tree of the index of the hook against PARENT. The tree
    leaves out a file of git add -N, as the commit does."""
    base = empty_tree(root) if parent is None else parent
    return patch_id(git(["diff-tree", *DIFF_OPTIONS, base, commit_tree(root)], root, plain_env()), root)


def commit_patch_id(root: Path, commit: str) -> str:
    """The patch ID of COMMIT against its one parent, or against the empty tree for a first commit."""
    parents = git(["rev-list", "--parents", "-n", "1", commit], root).split()[1:]
    base = parents[0] if parents else empty_tree(root)
    return patch_id(git(["diff-tree", *DIFF_OPTIONS, base, commit], root), root)


def amend_state() -> str:
    """`yes` for an amend, `no` for a new commit, and `maybe` when the gate cannot tell. Ps shows the words of each
    argument joined with spaces, so a word --amend after the text of -m may be a part of the message. /proc on Linux
    gives each argument whole, so there the gate can always tell."""
    argv = git_argv()
    if not is_amend(argv):
        return "no"
    if is_sure_amend(argv):
        return "yes"
    exact = exact_git_argv()
    if exact is not None:
        return "yes" if amend_in_exact(exact) else "no"
    return "maybe"


def is_merge_commit(root: Path, commit: str) -> bool:
    return len(git(["rev-list", "--parents", "-n", "1", commit], root, plain_env()).split()) > 2


def trailer_value(root: Path) -> str:
    """The one word of the trailer: tree:<tree> for a merge, and else patch:<id> of the change against the parent of
    the commit. An amend replaces HEAD, so its parent is the parent of HEAD, and an amend of a merge is a merge. When
    the gate cannot tell an amend, it stops, since the one word needs the parent."""
    if resolve(root, "MERGE_HEAD") is not None:
        return f"tree:{commit_tree(root)}"
    head = resolve(root, "HEAD")
    state = amend_state() if head is not None else "no"
    if state == "maybe":
        raise Stop("the gate cannot tell whether this commit is an amend, since a word of the command after the text "
                   "of the message looks like --amend, and the trailer needs the parent of the commit. Put --amend "
                   "before -m, or give the message with -F FILE")
    if state == "no":
        return f"patch:{staged_patch_id(root, head)}"
    if is_merge_commit(root, head):
        return f"tree:{commit_tree(root)}"
    return f"patch:{staged_patch_id(root, resolve(root, 'HEAD^'))}"


RELEASE_CHECK = "release-check"
RELEASE_TIMEOUT = 120


def rebasing(root: Path) -> bool:
    """True during a rebase. A reword replays an old commit on a HEAD that may lack the later raise of the version,
    and the release sees only the HEAD at the end."""
    return any((root / git(["rev-parse", "--git-path", name], root, plain_env()).strip()).exists()
               for name in ("rebase-merge", "rebase-apply"))


def release_check(root: Path, message: Path) -> None:
    """Run `just release-check` with the message of the commit, so that a commit whose type asks for a release
    that the release script cannot write stops here, not at the release after the push."""
    if resolve(root, "MERGE_HEAD") is not None or rebasing(root) or RELEASE_CHECK not in recipes(root):
        return
    env = plain_env()
    env["JN_RELEASE_MESSAGE"] = str(message.resolve())
    argv = git_argv()
    for name in ("JN_RELEASE_CLEANUP", "JN_RELEASE_EDITOR", "JN_RELEASE_AMEND"):
        env.pop(name, None)
    cleanup = cleanup_of(argv)
    if cleanup is not None:
        env["JN_RELEASE_CLEANUP"] = cleanup
    # Git sets GIT_EDITOR=: only when it runs no editor, but a person may have set it too. An option such as -e can
    # come after the text of -m or -F, where the gate cannot tell it from the text.
    if runs_editor(argv):
        env["JN_RELEASE_EDITOR"] = "1"
    elif not option_words(argv)[1]:
        env["JN_RELEASE_EDITOR"] = "unknown"
    head = resolve(root, "HEAD")
    if head is not None and is_amend(argv):
        # Only a sure amend replaces the message of HEAD. A word --amend in the text of the message leaves HEAD
        # counted, which asks for the same bump or a bigger one, and the check still stops on a tag on HEAD.
        sure = is_sure_amend(argv)
        if sure and len(git(["rev-list", "--parents", "-n", "1", head], root, plain_env()).split()) > 2:
            return  # An amend of a merge is a merge, and the release skips merge commits.
        env["JN_RELEASE_AMEND"] = "1" if sure else "maybe"
    try:
        run = subprocess.run(["just", RELEASE_CHECK], cwd=root, env=env, stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, errors="replace", timeout=RELEASE_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise Stop(f"`just {RELEASE_CHECK}` did not end in {RELEASE_TIMEOUT} seconds") from None
    if run.returncode != 0:
        lines = [line for line in run.stderr.splitlines() if line.startswith("release: ")] or run.stderr.splitlines()
        reason = " ".join(line.strip() for line in lines[-3:]) or f"exit {run.returncode}"
        raise Stop(f"`just {RELEASE_CHECK}` fails with the message of this commit: {reason}")


# The cleanup modes of git commit, for an empty message.
CLEANUP_MODES = ("default", "strip", "whitespace", "verbatim", "scissors")
# The characters that git picks from for core.commentChar=auto, in its order.
AUTO_COMMENT_CHARS = "#;@!$%^&|:"
# The scissors line of git, after the comment string.
SCISSORS = " ------------------------ >8 ------------------------"


def config(root: Path, key: str) -> str:
    return git(["config", "--get", key], root, plain_env(), check=False).strip()


def comment_strings(root: Path, text: str, editor: bool) -> List[str]:
    """The comment strings that git may use: core.commentString or core.commentChar, `#` by default. For `auto`,
    git takes the first character of its list that starts no line of the message that it gives the editor. Without
    an editor, that is TEXT. After an editor, git's own lines, such as its hint "Please enter the commit message",
    show the character. Without them, each character of the list may be the one."""
    for key in ("core.commentString", "core.commentChar"):
        value = config(root, key)
        if value and value != "auto":
            return [value]
        if value == "auto":
            if not editor:
                starts = {line[:1] for line in text.splitlines()}
                return [next((char for char in AUTO_COMMENT_CHARS if char not in starts), "#")]
            for line in text.splitlines():
                if line[:1] in AUTO_COMMENT_CHARS and (line[1:] == SCISSORS or " Please enter the " in line):
                    return [line[:1]]
            return list(AUTO_COMMENT_CHARS)
    return ["#"]


def config_true(root: Path, key: str) -> bool:
    value = config(root, key).lower()
    return value not in ("", "false", "no", "off", "0")


def stripspace(text: str, comment: Optional[str]) -> str:
    """The text as strbuf_stripspace of git leaves it: each comment line out when COMMENT is given, the spaces at
    the end of each line out, one blank line for each run of them, none at the start or the end."""
    out: List[str] = []
    for line in text.splitlines():
        if comment is not None and line.startswith(comment):
            continue
        line = line.rstrip()
        if not line and (not out or not out[-1]):
            continue
        out.append(line)
    while out and not out[-1]:
        out.pop()
    return "".join(line + "\n" for line in out)


def rest_is_empty(text: str) -> bool:
    """True when each line of TEXT is blank or a Signed-off-by line, as rest_is_empty of git commit reads it."""
    return all(not line.strip() or line.startswith("Signed-off-by: ") for line in text.splitlines())


def message_is_empty(text: str, mode: str, editor: bool, verbose: bool, commit: bool, comment: str,
                     template: Optional[str]) -> bool:
    """True when git stops the commit for the message TEXT, with the comment string COMMENT. git commit cuts the
    message at the scissors line for -v and for the mode scissors, then cleans it up. Then it reads the message as
    empty when each line is blank or a Signed-off-by line, and git merge when each line is blank. In the mode
    verbatim, only a message of no characters is empty. A message that starts with the cleaned TEMPLATE, with
    only such lines after it, is a template that the editor left as it was."""
    lines = text.splitlines()
    scissors = comment + SCISSORS
    if (verbose or (mode == "scissors" and editor)) and scissors in lines:
        text = "".join(line + "\n" for line in lines[:lines.index(scissors)])
    if mode == "verbatim":
        return not text
    strip = comment if mode == "strip" or (mode == "default" and editor) else None
    message = stripspace(text, strip)
    if not commit:
        return not message.strip()
    if rest_is_empty(message):
        return True
    if template is not None and editor:
        model = stripspace(template, strip)
        if model and message.startswith(model):
            return rest_is_empty(message[len(model):])
    return False


def read_template(root: Path, name: str, prefix: str) -> str:
    """The text of the template NAME. Git reads a relative path of -t from the folder where git ran, which it gives
    the hook in GIT_PREFIX as PREFIX, and a relative path of commit.template from the top of the repository, with a
    PREFIX of "". When the gate cannot read it, it stops the commit, since it cannot tell whether git stops it."""
    path = Path(name).expanduser()
    if not path.is_absolute():
        path = root / prefix / path
    try:
        return path.read_text(errors="replace")
    except OSError as error:
        raise Stop(f"the gate cannot read the template {name} ({error}), so it cannot tell whether git stops the "
                   "commit for a message that is the template. Give the template as an absolute path") from None


def may_be_empty(root: Path, text: str, argv: Sequence[str], exact: Optional[Sequence[str]] = None) -> bool:
    """True when git finds the message TEXT empty and stops the commit, as git does after this hook. The rules are
    in message_is_empty. With --allow-empty-message, no message is empty.

    EXACT is the argv with each argument whole, when the system can give it. git merge and the commands that are not
    git commit tell the editor in GIT_EDITOR, which git sets to `:` when it runs none. ARGV, from ps, may hide an
    option after the text of the message. When the readings that may apply disagree, the gate stops the commit."""
    words = exact if exact is not None else argv
    commit = "commit" in words
    verbose_config = config_true(root, "commit.verbose")
    template_name, prefix = None, ""
    if commit and exact is not None:
        options = exact_options(exact)
        if options["allow_empty"]:
            return False
        readings = [(options["cleanup"], bool(options["editor"]))]
        verbose = bool(options["verbose"]) or verbose_config
        if not (options["gives"] or options["amend"]):
            if options["template"]:
                template_name, prefix = str(options["template"]), os.environ.get("GIT_PREFIX", "")
            elif config(root, "commit.template"):
                template_name, prefix = config(root, "commit.template"), ""
    elif commit:
        sure, complete = option_words(argv)
        if any(len(word) >= len("--allow-empty-m") and "--allow-empty-message".startswith(word) for word in sure):
            return False
        given = cleanup_of(argv)
        if os.environ.get("GIT_EDITOR") != ":" or runs_editor(argv):
            editors = [True]
        else:
            editors = [False] if complete else [False, True]
        readings = [(given, editor) for editor in editors]
        verbose = verbose_config or any(word in ("-v", "--verbose") for word in sure)
    else:
        # git merge, or git commit run by another command of git: GIT_EDITOR tells the editor.
        given = None
        for index, word in enumerate(words):
            name, equals, rest = word.partition("=")
            if len(name) >= 3 and "--cleanup".startswith(name):
                given = rest if equals else (words[index + 1] if index + 1 < len(words) else "")
        readings = [(given, os.environ.get("GIT_EDITOR") != ":")]
        verbose = False
    template = read_template(root, template_name, prefix) if template_name is not None else None
    answers = set()
    for given, editor in readings:
        if given is None:
            given = config(root, "commit.cleanup") or "default"
        modes = [given] if given in CLEANUP_MODES else list(CLEANUP_MODES)
        for mode in modes:
            for comment in comment_strings(root, text, editor):
                answers.add(message_is_empty(text, mode, editor, verbose, commit, comment, template))
    if len(answers) > 1:
        raise Stop("the gate cannot tell whether git finds the message empty, so it cannot tell whether to add the "
                   "trailer. Either ps joins the words of each argument and an option may hide in the text of -m, "
                   "or core.commentChar is auto and the editor removed the hint of git. Give the message with "
                   "-F FILE and the options before it, or set core.commentChar")
    return answers == {True}


def add_trailer(root: Path, message: Path) -> None:
    """Put the one trailer of the gate at the end of the message. Each old trailer of the gate goes first, so an
    amend of a commit with a trailer has the new one alone."""
    value = trailer_value(root)
    # With --no-divider, a line --- in the message is text, so the trailer goes at the end, where git log reads it.
    git(["interpret-trailers", "--in-place", "--no-divider", "--if-exists", "replace", "--trailer",
         f"{TRAILER}: {value}", str(message)], root, plain_env())
    text = message.read_text(errors="surrogateescape")
    lines = text.splitlines(keepends=True)
    key = re.compile(rf"^{TRAILER}\s*:", re.IGNORECASE)
    marks = [index for index, line in enumerate(lines) if key.match(line)]
    if not marks:
        return
    # `--if-exists replace` replaces one old trailer only. The new one is the last, and each other trailer of the
    # gate in its block goes. A line above the block is text of the message, which git log does not read.
    keep = start = marks[-1]
    while start > 0 and lines[start - 1].strip():
        start -= 1
    drop = [index for index in marks if start <= index < keep]
    if drop:
        message.write_text("".join(line for index, line in enumerate(lines) if index not in drop),
                           errors="surrogateescape")


class NoBase(Stop):
    """The commits to check have no base branch."""


def github_default_branch(env: Mapping[str, str]) -> Optional[str]:
    """The default branch of the repository, from the event file of GitHub Actions, or None."""
    path = env.get("GITHUB_EVENT_PATH")
    if not path:
        return None
    try:
        event = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    branch = event.get("repository", {}).get("default_branch") if isinstance(event, dict) else None
    return branch if isinstance(branch, str) and branch else None


def in_ci(env: Mapping[str, str]) -> bool:
    return env.get("CI", "").lower() in ("true", "1") or env.get("GITHUB_ACTIONS") == "true"


def ci_range(root: Path, env: Mapping[str, str]) -> Tuple[Optional[str], str]:
    """The commits that `just ci-gate` checks, as BASE and HEAD. A BASE of None means all the commits of HEAD.

    The pre-push hook of the pre-commit framework gives the commits of the push in PRE_COMMIT_FROM_REF and
    PRE_COMMIT_TO_REF, or only PRE_COMMIT_LOCAL_BRANCH for a push of a new history, which the remote has no commit of.
    For an existing remote branch, JN_CI_BASE selects the PR target tip as base. It must be an ancestor of the
    pushed head, and each of its commits must be on the remote. PRE_COMMIT_TO_REF remains the head; a conflicting
    JN_CI_HEAD stops the push. Without that selection, the push range is unchanged. New-history pushes still check all
    commits. Outside a push, JN_CI_BASE and JN_CI_HEAD give the range. Else the base is the base branch on origin: the
    base of the pull request in GITHUB_BASE_REF, the default branch of the event of GitHub Actions, origin/HEAD,
    origin/main or origin/master, and last the upstream of the branch. BASE..HEAD holds the commits from the merge-base
    to HEAD. With none of them, NoBase stops."""
    if env.get("PRE_COMMIT_FROM_REF") and env.get("PRE_COMMIT_TO_REF"):
        if env.get("JN_CI_BASE"):
            def resolve(value: str, label: str) -> str:
                commit = git(["rev-parse", "--verify", "--quiet", "--end-of-options", f"{value}^{{commit}}"],
                             root, plain_env(), check=False).strip()
                if not commit:
                    raise Stop(f"{label} does not resolve to a commit: {value}")
                return commit

            base = resolve(env["JN_CI_BASE"], "JN_CI_BASE")
            head = resolve(env["PRE_COMMIT_TO_REF"], "pushed head")
            if env.get("JN_CI_HEAD") and resolve(env["JN_CI_HEAD"], "JN_CI_HEAD") != head:
                raise Stop("JN_CI_HEAD differs from the pushed head in PRE_COMMIT_TO_REF")
            try:
                git(["merge-base", "--is-ancestor", base, head], root, plain_env())
            except Stop as exc:
                raise Stop("JN_CI_BASE must be an ancestor of the pushed head") from exc
            # Each commit of the base must be on the remote already, so that each commit new to the remote stays in
            # BASE..HEAD. A base of HEAD, of a new commit or of a local branch ahead of the remote stops the push.
            remote = env.get("PRE_COMMIT_REMOTE_NAME")
            remotes = f"--remotes={remote}" if remote else "--remotes"
            if git(["rev-list", "-n", "1", base, "--not", remotes], root, plain_env()).strip():
                raise Stop(f"JN_CI_BASE contains commits that are not on the remote{' ' + remote if remote else ''}. Fetch the PR "
                           "target and give the SHA of its tip")
            count = git(["rev-list", "--count", f"{base}..{head}"], root, plain_env()).strip()
            print(f"ci-gate: JN_CI_BASE {base[:12]} selects {count} commits of the push", file=sys.stderr)
            return base, head
        return env["PRE_COMMIT_FROM_REF"], env["PRE_COMMIT_TO_REF"]
    if env.get("PRE_COMMIT_LOCAL_BRANCH"):
        return None, env["PRE_COMMIT_LOCAL_BRANCH"]
    head = env.get("JN_CI_HEAD") or "HEAD"
    if env.get("JN_CI_BASE"):
        return env["JN_CI_BASE"], head
    # The full names of the refs of origin, so that a local branch named origin/main cannot take their place.
    names = [f"refs/remotes/origin/{branch}" for branch in (env.get("GITHUB_BASE_REF"), github_default_branch(env))
             if branch]
    names += ["refs/remotes/origin/HEAD", "refs/remotes/origin/main", "refs/remotes/origin/master", "@{upstream}"]
    for name in names:
        if git(["rev-parse", "--verify", "--quiet", "--end-of-options", f"{name}^{{commit}}"], root, plain_env(),
               check=False).strip():
            return name, head
    raise NoBase("the commits to check have no base: there is no JN_CI_BASE, no origin/HEAD, origin/main or "
                 "origin/master, and the branch has no upstream. Give the base in JN_CI_BASE for one command, as "
                 "JN_CI_BASE=origin/main just ci-gate")


# The author of a commit by a GitHub App, such as dependabot[bot] or github-actions[bot]. GitHub gives it this e-mail.
BOT_EMAIL = re.compile(r"(?:[0-9]+\+)?[A-Za-z0-9][A-Za-z0-9-]*\[bot\]@users\.noreply\.github\.com")
# One word of the trailer: the patch ID of a change, `none` for an empty change, or the tree of a merge. The hashes
# are SHA-1 or SHA-256.
TRAILER_WORD = re.compile(r"(?:patch:(?:none|[0-9a-f]{40}|[0-9a-f]{64})|tree:(?:[0-9a-f]{40}|[0-9a-f]{64}))")

# How to fix a commit that fails the check. `just check` runs ci-gate, so the fix takes the bad commit off HEAD first.
TRAILER_FIX = ("To fix a commit, make it again through the gate. For the newest commit, run `git reset --soft HEAD~1`, "
               "then `just check`, then `git commit -C ORIG_HEAD`. For an older commit, run `git rebase -i` on its "
               "parent, mark the commit `edit`, do the same at the stop, then run `git rebase --continue`. The "
               "commits that come after it keep their trailers when the rebase has no conflict. When the commits are "
               "not yours, the base is wrong: give the base branch, as JN_CI_BASE=origin/develop")


def ever_had_stack(root: Path, commit: str) -> bool:
    """True when a commit that COMMIT can reach changed .agents/stack.json, so the gate was there before it. With
    --full-history, a merge that drops the file cannot hide the commit that added it."""
    return bool(git(["rev-list", "-1", "--full-history", commit, "--", STACK], root).strip())


def clean_merge(root: Path, commit: str, parents: List[str]) -> bool:
    """True when the merge COMMIT of two parents has the tree that git makes for them with no conflict, so it adds no
    change of its own."""
    if len(parents) != 2:
        return False
    run = subprocess.run(["git", "merge-tree", "--write-tree", "--no-messages", parents[0], parents[1]], cwd=root,
                         env=plain_env(), stdin=subprocess.DEVNULL, capture_output=True, text=True)
    tree = run.stdout.split("\n", 1)[0].strip()
    return run.returncode == 0 and tree == git(["rev-parse", f"{commit}^{{tree}}"], root).strip()


def exemption(root: Path, commit: str, parents: List[str], email: str) -> Optional[str]:
    """Why COMMIT needs no trailer, or None when it needs one."""
    if len(parents) > 1 and clean_merge(root, commit, parents):
        return ("a merge with no change of its own, which the check skips: GitHub makes the merge of a pull request "
                "without the gate")
    if BOT_EMAIL.fullmatch(email):
        return f"its author {email} is a GitHub bot, which commits without the gate"
    if not ever_had_stack(root, commit):
        return f"it is from before the gate: no commit before it has {STACK}"
    return None


def check_trailers(root: Path, base: Optional[str], head: str, notes: Optional[List[str]] = None) -> List[str]:
    """The problems of the commits in BASE..HEAD, or of all the commits of HEAD when BASE is None: each one needs one
    trailer of the gate, in the right form, that names its change. The reason for each exempt commit goes in NOTES."""
    if git(["rev-parse", "--is-shallow-repository"], root).strip() == "true":
        raise Stop("the clone is shallow, so the check cannot read the parents of the commits. Fetch the whole "
                   "history, as with fetch-depth: 0 in actions/checkout")
    problems = []
    span = head if base is None else f"{base}..{head}"
    for commit in git(["rev-list", "--reverse", "--end-of-options", span, "--"], root).split():
        fields = git(["log", "-1", "--format=%P%x00%ae%x00%s", commit], root).rstrip("\n").split("\0")
        parents, email, subject = fields[0].split(), fields[1], fields[2]
        name = f"{commit[:12]} ({subject})"
        why = exemption(root, commit, parents, email)
        if why is not None:
            if notes is not None:
                notes.append(f"{name} is exempt: {why}")
            continue
        values = git(["log", "-1", f"--format=%(trailers:key={TRAILER},valueonly,separator=%x00)", commit],
                     root).strip("\n").split("\0")
        values = [value.strip() for value in values if value.strip()]
        if not values:
            problems.append(f"{name} has no {TRAILER} trailer, so it did not pass the commit gate, for example a "
                            "commit made with git commit -n, or by git revert --no-edit")
            continue
        if len(values) > 1:
            problems.append(f"{name} has {len(values)} {TRAILER} trailers, and the gate writes one, for example after "
                            "a squash of two commits")
            continue
        words = values[0].split()
        odd = [word for word in words if not TRAILER_WORD.fullmatch(word)]
        if odd:
            problems.append(f"{name} has a {TRAILER} trailer that the gate did not write: {values[0]!r}. Each word "
                            "must be patch:<patch ID> or tree:<tree>")
            continue
        if len(words) != 1:
            problems.append(f"{name} has a {TRAILER} trailer of {len(words)} words: {values[0]!r}, and the gate "
                            "writes one word")
            continue
        if len(parents) > 1:
            expected, kind = git(["rev-parse", f"{commit}^{{tree}}"], root).strip(), "tree"
        else:
            expected, kind = commit_patch_id(root, commit), "patch"
        if words != [f"{kind}:{expected}"]:
            problems.append(f"{name} changed after the commit gate passed it: its {kind} is {expected}, and the "
                            f"trailer names {values[0]}, for example after a rebase with a conflict or an amend "
                            "with git commit -n")
    return problems


# The command that runs the gate, as the hooks run it.
GATE_COMMAND = ("uv run --no-project --quiet --no-python-downloads --python '>=3.9' python "
                ".agents/skills/gcm/scripts/commit_gate.py")

# The config of the framework, and the hooks of it that the tasker role needs: the stages and the entry of each one.
# The gate runs before a commit and before the commit of a merge.
CONFIG = ".pre-commit-config.yaml"
# The pre-push hook runs pre_push.py, which runs just ci less what a pass of just check did. The entry `just ci` of an
# older config counts too: it runs all of just ci.
PRE_PUSH_COMMAND = ("uv run --no-project --quiet --no-python-downloads --python '>=3.9' python "
                    ".agents/skills/gcm/scripts/pre_push.py")
CONFIG_HOOKS = {"commit-gate": (("pre-commit", "pre-merge-commit"), (GATE_COMMAND,)),
                "commit-gate-trailer": (("commit-msg",), (f"{GATE_COMMAND} --hook commit-msg",)),
                "just-ci": (("pre-push",), (PRE_PUSH_COMMAND, "just ci"))}

# The stages of the gate, the stages that the tasker role installs, and the text that each hook of the pre-commit
# framework holds. The pre-push hook runs pre_push.py, not the gate.
HOOK_STAGES = ("pre-commit", "pre-merge-commit", "commit-msg")
INSTALLED_STAGES = HOOK_STAGES + ("pre-push",)
FRAMEWORK_MARK = "# File generated by pre-commit"


def framework_hook_problem(root: Path, stage: str) -> Optional[str]:
    """Why the git hook of the stage does not run the pre-commit framework, or None when it does. The hook runs the
    Python of its INSTALL_PYTHON line when that file is there, else pre-commit from PATH."""
    hook = root / git(["rev-parse", "--git-path", f"hooks/{stage}"], root, plain_env()).strip()
    try:
        text = hook.read_text(errors="replace")
    except OSError:
        return f"{stage}: there is no hook"
    if FRAMEWORK_MARK not in text or f"--hook-type={stage}" not in text:
        return f"{stage}: the hook is not a {stage} hook of the pre-commit framework"
    if f"--config={CONFIG}" not in text:
        return f"{stage}: the hook runs a config other than {CONFIG}"
    python = next((line.partition("=")[2].strip() for line in text.splitlines()
                   if line.startswith("INSTALL_PYTHON=")), "")
    python = python.strip("'\"")
    if python and os.access(python, os.X_OK):
        run = subprocess.run([python, "-c", "import pre_commit"], stdin=subprocess.DEVNULL, capture_output=True)
        return None if run.returncode == 0 else f"{stage}: {python} of the hook has no pre-commit"
    return None if shutil.which("pre-commit") else f"{stage}: pre-commit is not on PATH"


# The script that reads the config with the loader of pre-commit, in the Python of the framework, and prints the
# hooks of its local entries. A hook with no stages of its own runs in the default_stages of the config.
LOAD_CONFIG = """import json, sys
from pre_commit.clientlib import load_config
config = load_config(sys.argv[1])
print(json.dumps([{"id": h["id"], "entry": h.get("entry"), "stages": h.get("stages") or config["default_stages"]}
                  for r in config["repos"] if r["repo"] == "local" for h in r["hooks"]]))"""


def framework_python(root: Path) -> Optional[str]:
    """The Python that has pre-commit: the INSTALL_PYTHON of the pre-commit hook, else the Python of the pre-commit
    on PATH, from its first line."""
    hook = root / git(["rev-parse", "--git-path", "hooks/pre-commit"], root, plain_env()).strip()
    try:
        lines = hook.read_text(errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        if line.startswith("INSTALL_PYTHON="):
            python = line.partition("=")[2].strip().strip("'\"")
            if python and os.access(python, os.X_OK):
                return python
    program = shutil.which("pre-commit")
    if program:
        try:
            lines = Path(program).read_text(errors="replace").splitlines()[:2]
        except OSError:
            return None
        first = lines[0] if lines else ""
        words = first[2:].split() if first.startswith("#!") else []
        # pip and uv write this launcher when the path of the Python is long or has a space.
        if len(lines) > 1 and lines[1].startswith("'''exec'"):
            try:
                words = shlex.split(lines[1])[1:2]
            except ValueError:
                words = []
        elif words[:1] and Path(words[0]).name == "env":
            words = [shutil.which(words[1]) or ""] if len(words) > 1 else []
        python = words[0] if words else ""
        # A shell wrapper, as of pyenv, asdf or mise, names no Python on its first line.
        if python and os.access(python, os.X_OK) and has_pre_commit(python):
            return python
    return None


def has_pre_commit(python: str) -> bool:
    # In an empty folder, so that no pre_commit folder of the current folder can answer for the module.
    with tempfile.TemporaryDirectory(prefix="commit-gate-python-") as away:
        run = subprocess.run([python, "-c", "import pre_commit"], stdin=subprocess.DEVNULL, capture_output=True,
                             cwd=away)
    return run.returncode == 0


def config_problems(root: Path) -> List[str]:
    """The hooks of the tasker role that the config lacks, read by the loader of pre-commit. Each one must be in a
    local entry, with its entry and its stage. The installer keys the entries of `repos` by `repo`, so a `local`
    entry of the project takes the place of the entry of the role, and its hooks go."""
    if not (root / CONFIG).is_file():
        return [f"there is no {CONFIG}"]
    python = framework_python(root)
    if python is None:
        return [f"no Python with pre-commit can read {CONFIG}: the pre-commit hook names none, and the first line "
                "of the pre-commit on PATH names none"]
    # Outside the project, so that a json.py or a pre_commit folder of the project cannot take the place of the module.
    with tempfile.TemporaryDirectory(prefix="commit-gate-config-") as away:
        run = subprocess.run([python, "-c", LOAD_CONFIG, str((root / CONFIG).resolve())], stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, cwd=away)
    try:
        hooks = json.loads(run.stdout) if run.returncode == 0 else None
    except ValueError:
        hooks = None
    if not isinstance(hooks, list):
        return [f"pre-commit cannot read {CONFIG}: {(run.stderr.strip().splitlines() or ['no output'])[-1]}"]
    problems = []
    for name, (stages, entries) in CONFIG_HOOKS.items():
        for stage in stages:
            if not any(isinstance(h, dict) and h.get("id") == name and h.get("entry") in entries
                       and stage in (h.get("stages") or ()) for h in hooks):
                problems.append(f"{CONFIG} has no local hook {name} that runs {entries[0]} for the stage {stage}. A "
                                "repo: local entry of the project takes the place of the entry of the tasker role, so "
                                "copy the hooks of .agents/skills/gcm/assets/pre-commit-config.yaml into it")
    return problems


def check_hooks(root: Path) -> List[str]:
    """The problems with the hooks of the gate: one line for each stage whose hook does not run pre-commit. With
    core.hooksPath set, as husky sets it, pre-commit refuses to install, so there is no problem to fix here: the
    hooks of that folder must run the gate."""
    hooks_path = git(["config", "--get", "core.hooksPath"], root, plain_env(), check=False).strip()
    if hooks_path:
        print(f"commit gate: core.hooksPath is {hooks_path}, so pre-commit installs no hook. Run "
              f"{GATE_COMMAND} from the pre-commit and pre-merge-commit hooks of that folder, {GATE_COMMAND} --hook "
              f"commit-msg from its commit-msg hook, and {PRE_PUSH_COMMAND} from its pre-push hook.", file=sys.stderr)
        return []
    hooks = [problem for stage in INSTALLED_STAGES for problem in [framework_hook_problem(root, stage)] if problem]
    return config_problems(root) + hooks


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="The commit gate.")
    parser.add_argument("--hook", choices=HOOK_STAGES, default="pre-commit")
    parser.add_argument("message", nargs="?", help="the message file, for the commit-msg hook")
    parser.add_argument("--trailers", nargs="*", metavar="BASE HEAD",
                        help="check the trailers of BASE..HEAD; with no BASE and HEAD, of the range of ci_range")
    parser.add_argument("--check-hooks", action="store_true",
                        help="check that the pre-commit framework runs the four hooks of the tasker role")
    args = parser.parse_args(argv)
    if args.check_hooks and not git(["rev-parse", "--show-toplevel"], Path.cwd(), plain_env(), check=False):
        # Outside a repository there is no hook to install yet. The first just install after git init installs them.
        print("commit gate: this folder is not in a Git repository, so it has no hooks yet", file=sys.stderr)
        return 0
    try:
        root = Path(git(["rev-parse", "--show-toplevel"], Path.cwd(), plain_env()).strip())
        if args.trailers is not None:
            if len(args.trailers) not in (0, 2):
                parser.error("--trailers takes BASE and HEAD, or nothing")
            try:
                base, head = args.trailers if args.trailers else ci_range(root, os.environ)
            except NoBase as stop:
                if in_ci(os.environ):
                    raise
                # A clone with no remote has no pull request yet, so there is no commit to compare.
                print(f"ci-gate: skipped, {stop}", file=sys.stderr)
                return 0
            notes: List[str] = []
            problems = check_trailers(root, base, head, notes)
            for note in notes:
                print(f"ci-gate: {note}", file=sys.stderr)
            for problem in problems:
                print(f"gate trailers: {problem}", file=sys.stderr)
            if problems:
                print(f"gate trailers: {TRAILER_FIX}", file=sys.stderr)
            return 1 if problems else 0
        problems = check_hooks(root) if args.check_hooks else []
        if not args.check_hooks:
            gate(root)
            if args.hook == "commit-msg":
                if args.message is None:
                    raise Stop("the commit-msg hook needs the message file")
                text = Path(args.message).read_text(errors="replace")
                if may_be_empty(root, text, git_argv(), exact_git_argv()):
                    # git stops a commit with an empty message after this hook, unless the trailer fills it.
                    print("commit gate: the message is empty, so git stops the commit, and the gate adds no trailer. "
                          "A commit that git makes anyway has no trailer, and just ci-gate names it", file=sys.stderr)
                    return 0
                release_check(root, Path(args.message))
                add_trailer(root, Path(args.message))
    except Stop as stop:
        problems = [str(stop)]
    for problem in problems:
        print(f"commit gate: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
