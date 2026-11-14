"""The gate guard: an agent hook that stops the commands that go around the commit gate.

The `PreToolUse` hooks of Claude Code and Codex run it before each tool call, with the hook input as JSON on stdin.
It exits with 2 and says why on stderr to stop the call, and with 0 to let it run. It never checks records: the
commit gate does that. It is a best effort, since a shell has many ways to run a command. It stops:

- `git commit` with `--no-verify` or `-n`, and `git merge` or `git pull` with `--no-verify`, also through an alias,
  `sh -c`, `eval` or `git rebase --exec`;
- a setting of `core.hooksPath`, by `git -c`, `git config` or a `GIT_CONFIG_` variable, and `git commit-tree` and
  `git update-ref`;
- a write to a log folder, `.git/hooks`, `.agents/targets/required.txt`, `.pre-commit-config.yaml` or the settings of
  the agent hooks, by a shell command, or by a file tool of Claude Code. Codex runs the guard for its shell only.

A command that only reads, such as `git log --grep=hooksPath` or `cp .claude/settings.json backup.json`, runs. When
the guard itself fails, it lets the call run, since the commit gate still checks the commit.

Usage: gate_guard.py, with the hook input on stdin.
"""

from __future__ import annotations

import functools
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
from typing import Dict, List, Optional, Sequence, Tuple

# The paths that only the installer, jlog and the record hooks write.
PROTECTED = (".agents/log", ".git/hooks", ".agents/targets/required.txt", ".pre-commit-config.yaml",
             ".claude/settings.json", ".claude/settings.local.json", ".codex/hooks.json", ".codex/config.toml")

# The programs that change each file that they name, and the programs that change only the last one.
WRITE_ALL = {"mv", "rm", "tee", "touch", "truncate", "chmod", "chown", "unlink", "mkdir", "rmdir", "shred"}
WRITE_LAST = {"cp", "ln", "install", "rsync", "scp"}

# The words in front of a program that run it, with their options that take a value.
PREFIXES: Dict[str, set] = {"env": {"-u", "-C", "--unset", "--chdir"}, "command": set(), "exec": {"-a"},
                            "nohup": set(), "builtin": set(), "time": {"-f", "-o"}, "nice": {"-n"},
                            "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "-T"},
                            "timeout": {"-s", "-k", "--signal", "--kill-after"}, "doas": {"-u", "-C"}, "xargs": {
                                "-I", "-L", "-n", "-P", "-s", "-d", "-E", "-a"}}
# The prefixes whose first word after the options is not the program, such as the time limit of timeout.
PREFIX_ARGUMENT = {"timeout"}

SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}

# The options of git that come before the command and take a value.
GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}

# The short options of git commit that take a value. In a cluster such as -am, the rest of the cluster after one of
# them is its value.
COMMIT_VALUE_FLAGS = set("mFCctSu")

SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "|&", ";;", "{", "}"}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# A here-doc: << and its word, but not the here-string <<< and not a shift such as 1 << 2.
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
# The word that takes the place of the Nth $(...) or `...`. The walk of the commands fills in a plain
# `git rev-parse` in the folder that the cds lead to. Any other stays a $ word, so a path that holds it is unknown.
SUBSTITUTION = "$__substitution{}__"
FILLED = re.compile(r"^__substitution(\d+)__$")
VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")
# The variables of the environment whose value the guard takes as known.
KNOWN_VARIABLES = ("HOME", "TMPDIR", "CLAUDE_PROJECT_DIR")
# The markers of a subshell, ( and ), in the list of simple commands.
OPEN, CLOSE = ["("], [")"]
# The words that start a part of a compound command, in front of a program.
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!"}
# The short options of sed, perl and ruby that take a value. In a cluster such as -ne, the rest is its value.
VALUE_FLAGS = {"sed": set("ef"), "perl": set("eEMmIlx0C"), "ruby": set("eEIrCx0")}


class Blocked(Exception):
    pass


def without_heredocs(command: str) -> Tuple[str, List[str]]:
    """The command with the body of each here-doc taken out and each line end made a `;`, and the bodies that a
    shell runs, such as the body of `bash <<EOF`. A line that ends with a backslash goes on. A line end inside
    quotes stays in the quoted word. A comment is dropped, so an apostrophe in it is not a quote."""
    kept: List[str] = []
    bodies: List[str] = []
    end: Optional[str] = None
    body: List[str] = []
    runs = False
    for line in command.split("\n"):
        if end is not None:
            if line.strip() == end:
                if runs:
                    bodies.append("\n".join(body))
                end = None
            else:
                body.append(line)
            continue
        kept.append(line)
        found = next((m for m in HEREDOC.finditer(line) if outside_quotes(line, m.start())), None)
        if found and "((" not in line[:found.start()]:
            end, body = found.group(2), []
            before = segments(line[:found.start()])
            words = program_of(before[-1]) if before else []
            runs = bool(words) and name_of(words[0]) in SHELLS
    if end is not None and runs:
        bodies.append("\n".join(body))
    text = ""
    for line in kept:
        text += line[:-1] if line.endswith("\\") else line + "\n"
    out: List[str] = []
    quote: Optional[str] = None
    i = 0
    while i < len(text):
        char = text[i]
        if quote == "'":
            quote = None if char == "'" else quote
        elif char == "\\":
            out.append(text[i:i + 2])
            i += 2
            continue
        elif quote == '"':
            quote = None if char == '"' else quote
        elif char in "'\"":
            quote = char
        elif char == "#" and (i == 0 or text[i - 1] in " \t\n;&|("):
            stop = text.find("\n", i)
            i = len(text) if stop < 0 else stop
            continue
        elif char == "\n":
            out.append(" ; ")
            i += 1
            continue
        out.append(char)
        i += 1
    return "".join(out), bodies


def outside_quotes(line: str, position: int) -> bool:
    """True when POSITION of LINE is outside quotes, so that a `<<` in a message is not a here-doc."""
    quote: Optional[str] = None
    i = 0
    while i < position:
        char = line[i]
        if quote == "'":
            quote = None if char == "'" else quote
        elif char == "\\":
            i += 1
        elif quote == '"':
            quote = None if char == '"' else quote
        elif char in "'\"":
            quote = char
        i += 1
    return quote is None


def rev_parse_value(text: str, cwd: str) -> Optional[str]:
    """The output of TEXT when it is a plain `git rev-parse`, which only reads, such as `git rev-parse --git-path
    hooks`. Other commands are not run, and give None."""
    words = split(text)
    if words[:2] != ["git", "rev-parse"] or any(c in text for c in ";&|<>`$()"):
        return None
    # The folder may not exist yet, as after `mkdir -p sub && cd sub`. Absolute paths from the nearest folder that
    # exists name the same places.
    while cwd and not os.path.isdir(cwd):
        cwd = os.path.dirname(cwd)
    try:
        run = subprocess.run(["git", "rev-parse", "--path-format=absolute", *words[2:]], cwd=cwd or None,
                             stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = run.stdout.splitlines()
    return lines[0] if run.returncode == 0 and len(lines) == 1 else None


def substitutions(command: str):
    """The command with each $(...) and `...` put in place of one word, SUBSTITUTION with its number, and the text
    of each of them."""
    out, inner, i, quote = [], [], 0, None
    while i < len(command):
        char = command[i]
        if quote == "'":
            quote = None if char == "'" else quote
        elif char == "'" and quote is None:
            quote = "'"
        elif char == '"':
            quote = None if quote == '"' else '"'
        if quote != "'" and command.startswith("$(", i):
            depth, j = 1, i + 2
            while j < len(command) and depth:
                depth += {"(": 1, ")": -1}.get(command[j], 0)
                j += 1
            inner.append(command[i + 2:j - 1])
            out.append(SUBSTITUTION.format(len(inner) - 1))
            i = j
            continue
        if quote != "'" and char == "`":
            j = command.find("`", i + 1)
            j = len(command) if j < 0 else j
            inner.append(command[i + 1:j])
            out.append(SUBSTITUTION.format(len(inner) - 1))
            i = j + 1
            continue
        out.append(char)
        i += 1
    return "".join(out), inner


OPERATORS = ("&>>", "<<<", "&&", "||", ";;", "|&", ">>", "&>", ">|", "<<", "<&", ">&")
PUNCTUATION = set(";&|()<>")


def operators(word: str) -> List[str]:
    """A run of punctuation, such as `);` from shlex, split into its operators. Other words stay whole. A quoted
    word that holds only punctuation is split too, which is harmless: it holds no command."""
    if not word or not set(word) <= PUNCTUATION:
        return [word]
    parts, i = [], 0
    while i < len(word):
        match = next((op for op in OPERATORS if word.startswith(op, i)), word[i])
        parts.append(match)
        i += len(match)
    return parts


def segments(command: str, marks: bool = False) -> List[List[str]]:
    """The simple commands of a shell line, as lists of words. Text that shlex cannot split counts as plain words,
    so a quote that never closes does not hide a command. With MARKS, a ( and a ) of a subshell come as OPEN and
    CLOSE."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>")
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        words = [part for word in lexer for part in operators(word)]
    except ValueError:
        words = command.split()
    found: List[List[str]] = [[]]
    for word in words:
        if marks and word in ("(", ")"):
            found += [list(OPEN if word == "(" else CLOSE), []]
        elif word in SEPARATORS:
            found.append([])
        else:
            found[-1].append(word)
    return [segment for segment in found if segment]


def name_of(word: str) -> str:
    return posixpath.basename(word)


def program_of(words: List[str]) -> List[str]:
    """The words from the program on: without the assignments such as A=1 and the prefixes such as env."""
    rest = list(words)
    while rest:
        word, name = rest[0], name_of(rest[0])
        if ASSIGNMENT.match(word) or word in KEYWORDS:
            rest.pop(0)
        elif name in PREFIXES:
            rest.pop(0)
            while rest and rest[0].startswith("-"):
                option = rest.pop(0)
                if option in PREFIXES[name] and rest:
                    rest.pop(0)
            if name in PREFIX_ARGUMENT and rest:
                rest.pop(0)
        else:
            break
    return rest


def alias_of(name: str, cwd: str, defined: Dict[str, str]) -> Optional[str]:
    """The text of the git alias NAME, from `git -c` or from the config, or None."""
    if name in defined:
        return defined[name]
    try:
        run = subprocess.run(["git", "config", "--get", f"alias.{name}"], cwd=cwd, stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return run.stdout.strip() if run.returncode == 0 and run.stdout.strip() else None


def split(text: str) -> List[str]:
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def has_abbreviation(words: Sequence[str], option: str, shortest: str) -> bool:
    """True when a word is OPTION or an abbreviation of it that git takes, at least as long as SHORTEST."""
    return any(len(word) >= len(shortest) and option.startswith(word) for word in words)


def commit_skips_hooks(args: Sequence[str]) -> bool:
    for word in args:
        if word == "--":
            return False
        if word.startswith("-") and not word.startswith("--"):
            for flag in word[1:]:
                if flag == "n":
                    return True
                if flag in COMMIT_VALUE_FLAGS:
                    break
    # --no-verify and the abbreviations that git takes. --no-ver is also --no-verbose.
    return has_abbreviation(args, "--no-verify", "--no-veri")


def sets_hooks_path(setting: str) -> bool:
    return setting.lower().startswith("core.hookspath")


def check_git(args: List[str], cwd: str, depth: int = 0) -> None:
    rest = list(args)
    aliases: Dict[str, str] = {}
    while rest and rest[0].startswith("-"):
        option = rest.pop(0)
        value = None
        if option in GIT_VALUE_OPTIONS and rest:
            value = rest.pop(0)
        elif option.startswith("-c") and len(option) > 2:
            option, value = "-c", option[2:]
        elif option.startswith("--config-env="):
            option, value = "--config-env", option.split("=", 1)[1]
        if option in ("-c", "--config-env") and value:
            if sets_hooks_path(value):
                raise Blocked("core.hooksPath moves the git hooks, and the commit gate with them. Leave it alone")
            if value.lower().startswith("alias.") and "=" in value:
                key, text = value[len("alias."):].split("=", 1)
                aliases[key] = text
    if not rest:
        return
    name, sub = rest[0], rest[1:]
    if name == "commit" and commit_skips_hooks(sub):
        raise Blocked("`git commit --no-verify` skips the commit gate. Commit without it, and run the target or the "
                      "step that the gate names")
    if name in ("merge", "pull") and has_abbreviation(sub, "--no-verify", "--no-veri"):
        raise Blocked(f"`git {name} --no-verify` skips the gate of the merge. Merge without it")
    if name in ("commit-tree", "update-ref"):
        raise Blocked(f"`git {name}` makes a commit or moves a branch around the commit gate. Use `git commit`")
    if name == "config":
        # A key with a value sets it. `git config core.hooksPath` alone only reads it.
        plain, skip = [], False
        for word in sub:
            if skip:
                skip = False
            elif word in ("-f", "--file", "--blob", "--type", "--default", "--comment"):
                skip = True
            elif not word.startswith("-"):
                plain.append(word)
        # git 2.46 and later also take `git config set KEY VALUE`.
        if plain[:1] == ["set"]:
            plain = plain[1:] + ["value"]
        if plain and sets_hooks_path(plain[0]) and (len(plain) > 1 or "--unset" not in sub and any(
                w in sub for w in ("--add", "--replace-all"))):
            raise Blocked("core.hooksPath moves the git hooks, and the commit gate with them. Leave it alone")
    if name == "rebase":
        for index, word in enumerate(sub):
            if word in ("-x", "--exec") and index + 1 < len(sub):
                check_command(sub[index + 1], cwd)
            elif word.startswith("--exec="):
                check_command(word.split("=", 1)[1], cwd)
    if depth < 3 and name not in ("commit", "merge", "pull", "config", "rebase"):
        expanded = alias_of(name, cwd, aliases)
        if expanded and expanded.startswith("!"):
            check_command(expanded[1:] + " " + shlex.join(sub), cwd, depth + 1)
        elif expanded:
            check_git(split(expanded) + sub, cwd, depth + 1)


@functools.lru_cache(maxsize=None)
def places(cwd: str) -> Tuple[Tuple[str, str], ...]:
    """Each protected path of the repository of CWD, with its real place. The hooks and the shared log folder are
    in the main checkout, also for a worktree. Outside a repository, the paths are under CWD."""
    root, common = os.path.realpath(cwd), None
    try:
        run = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir"],
                             cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)
        if run.returncode == 0 and len(run.stdout.splitlines()) == 2:
            root, common = (os.path.realpath(line) for line in run.stdout.splitlines())
    except (OSError, subprocess.SubprocessError):
        pass
    found = [(path, os.path.join(root, path)) for path in PROTECTED]
    if common:
        found.append((".git/hooks", os.path.join(common, "hooks")))
        if os.path.basename(common) == ".git":
            found.append((".agents/log", os.path.join(os.path.dirname(common), ".agents/log")))
    return tuple(found)


def protected_path(word: str, cwd: str, here: Optional[str] = None) -> Optional[str]:
    """The protected path that WORD names, in the repository of CWD, or None. A relative path starts at HERE, the
    folder after any cd, or else at CWD. A path of another repository, such as the hooks of a scratch repository,
    is not protected."""
    text = word.replace("\\", "/")
    if "=" in text and not text.startswith("/"):
        text = text.split("=", 1)[1]
    # A variable whose value is not known, or a relative path after a cd to an unknown folder, could be any path.
    # The guard lets it run, since the commit gate still checks the commit.
    if not text or "$" in text or "`" in text or text.startswith("~") or (here == "" and not os.path.isabs(text)):
        return None
    full = os.path.realpath(os.path.join(here or cwd, text))
    for path, place in places(cwd):
        if full == place or full.startswith(place + os.sep):
            return path
    return None


def raise_write(path: str) -> None:
    raise Blocked(f"{path} is written only by the installer, jlog and the record hooks, so the commit gate can "
                  "trust it. Ask the person to change it")


def check_writes(words: List[str], rest: List[str], cwd: str, here: str) -> None:
    # A redirection writes to the word after it, whatever the program.
    for index, word in enumerate(words[:-1]):
        if word in (">", ">>", ">|", "&>", "&>>") or (word.endswith(">") and word[:-1].isdigit()):
            path = protected_path(words[index + 1], cwd, here)
            if path:
                raise_write(path)
    if not rest:
        return
    program = name_of(rest[0])
    args = [word for word in rest[1:] if not word.startswith("-")]
    if program in VALUE_FLAGS:
        in_place = any(w.startswith("--in-place") or in_cluster(w, VALUE_FLAGS[program]) for w in rest[1:])
        targets = args if in_place else []
    elif program == "dd":
        targets = [w for w in rest[1:] if w.startswith("of=")]
    elif program in WRITE_ALL:
        targets = args
    elif program in WRITE_LAST:
        targets = args[-1:]
    else:
        targets = []
    for word in targets:
        path = protected_path(word, cwd, here)
        if path:
            raise_write(path)


def in_cluster(word: str, value_flags: set) -> bool:
    """True when a short option cluster such as -pi has -i before any option that takes a value."""
    if not word.startswith("-") or word.startswith("--"):
        return False
    for flag in word[1:]:
        if flag == "i":
            return True
        if flag in value_flags:
            return False
    return False


def expand(word: str, known: Dict[str, str], inner: List[str], here: str) -> str:
    """WORD with each known variable put in, and a leading ~ as HOME when it is known. A substitution that is a plain
    `git rev-parse` gets its output, run in HERE. Other variables and substitutions stay."""
    if word.startswith("~/") and "HOME" in known:
        word = known["HOME"] + word[1:]

    def value(match) -> str:
        name = match.group(1) or match.group(2)
        filled = FILLED.match(name)
        if filled:
            found = rev_parse_value(inner[int(filled.group(1))], here) if here else None
            return found if found is not None else match.group(0)
        return known.get(name, match.group(0))

    return VARIABLE.sub(value, word)


def check_command(command: str, cwd: str, depth: int = 0) -> None:
    if depth > 4:
        return
    command, bodies = without_heredocs(command)
    command, inner = substitutions(command)
    for text in inner + bodies:
        check_command(text, cwd, depth + 1)
    here, before = cwd, cwd
    known = {name: os.environ[name] for name in KNOWN_VARIABLES if os.environ.get(name)}
    saved: List[tuple] = []
    for words in segments(command, marks=True):
        # A subshell keeps its cd and its variables to itself.
        if words == OPEN:
            saved.append((here, before, dict(known)))
            continue
        if words == CLOSE:
            if saved:
                here, before, known = saved.pop()
            continue
        if here:
            known["PWD"] = here
        else:
            known.pop("PWD", None)
        words = [expand(word, known, inner, here) for word in words]
        # A GIT_CONFIG_ variable can set core.hooksPath for every later git command, also through export.
        settings = [w for w in words if ASSIGNMENT.match(w) and w.upper().startswith("GIT_CONFIG")]
        if any("hookspath" in w.lower() for w in settings):
            raise Blocked("core.hooksPath moves the git hooks, and the commit gate with them. Leave it alone")
        rest = program_of(words)
        if not rest or rest[0] == "export":
            for word in (rest[1:] if rest else words):
                if ASSIGNMENT.match(word):
                    name, value = word.split("=", 1)
                    known[name] = value
            if not rest:
                continue
        # A cd changes the folder of the commands after it. The guard runs before the command, so the folder may
        # not exist yet. A folder that is not known makes later relative paths unknown.
        if rest[0] == "cd" and len(rest) <= 2:
            target = rest[1] if len(rest) == 2 else known.get("HOME", "$HOME")
            if target == "-":
                here, before = before, here
            elif "$" in target or target.startswith("~") or here == "" and not os.path.isabs(target):
                here, before = "", here
            else:
                here, before = os.path.normpath(os.path.join(here, target)), here
            continue
        check_writes(words, rest, cwd, here)
        program = name_of(rest[0])
        if program == "git":
            check_git(rest[1:], here or cwd)
        elif program == "eval":
            check_command(" ".join(rest[1:]), here or cwd, depth + 1)
        elif program in SHELLS:
            for index, word in enumerate(rest[1:-1], start=1):
                if word.startswith("-") and not word.startswith("--") and "c" in word:
                    check_command(rest[index + 1], here or cwd, depth + 1)
                    break


def command_of(tool_input: dict) -> Optional[str]:
    """The shell line of a tool call: `command` in Claude Code, `command` or `cmd` in Codex. A list such as
    ["bash", "-lc", LINE] gives LINE."""
    value = tool_input.get("command", tool_input.get("cmd"))
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return shlex.join(value)
    return value if isinstance(value, str) else None


def check(payload: dict, cwd: str) -> None:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    command = command_of(tool_input)
    if command is not None:
        check_command(command, cwd)
    for key in ("file_path", "notebook_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and protected_path(value, cwd):
            raise_write(protected_path(value, cwd))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        cwd = payload.get("cwd")
        cwd = cwd if isinstance(cwd, str) and os.path.isdir(cwd) else os.getcwd()
        check(payload, cwd)
    except Blocked as blocked:
        print(f"gate guard: {blocked}.", file=sys.stderr)
        return 2
    except Exception as error:  # A fault of the guard lets the call run: the commit gate still checks.
        print(f"gate guard: could not check the call ({error!r}), so it runs", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
