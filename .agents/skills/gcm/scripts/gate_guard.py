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

It asks the person before `just record-skip` or `record_result.py skip`, which let a tree through without a
record. Claude Code shows the question. Codex has no question for a hook, so there the guard stops the call and the
agent asks the person to run the command. It stops `record_result.py hook`, which only the harness runs, `just
record` in Claude Code, a record command that changes a variable of the harness, and a write to the sessions folder
of Codex.

A command that only reads, such as `git log --grep=hooksPath` or `cp .claude/settings.json backup.json`, runs. When
the guard itself fails, it lets the call run, since the commit gate still checks the commit.

Usage: gate_guard.py, with the hook input on stdin.
"""

from __future__ import annotations

import fnmatch
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
PROTECTED = (".agents/log", ".git/hooks", ".git/config", ".agents/targets/required.txt", ".pre-commit-config.yaml",
             ".claude/settings.json", ".claude/settings.local.json", ".codex/hooks.json", ".codex/config.toml")

# The programs that change each file that they name, and the programs that change only the last one.
WRITE_ALL = {"mv", "rm", "tee", "touch", "truncate", "chmod", "chown", "unlink", "mkdir", "rmdir", "shred"}
WRITE_LAST = {"cp", "ln", "install", "rsync", "scp"}

# The words in front of a program that run it, with their options that take a value.
PREFIXES: Dict[str, set] = {"env": {"-u", "-C", "--unset", "--chdir"}, "command": set(), "exec": {"-a"},
                            "nohup": set(), "builtin": set(), "time": {"-f", "-o"}, "nice": {"-n", "--adjustment"},
                            "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "-T"},
                            "timeout": {"-s", "-k", "--signal", "--kill-after"}, "doas": {"-u", "-C"}, "xargs": {
                                "-I", "-L", "-n", "-P", "-s", "-d", "-E", "-a"}}
# The prefixes whose first word after the options is not the program, such as the time limit of timeout.
PREFIX_ARGUMENT = {"timeout"}

SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}

# The programs that take git only as text, such as the pattern of grep.
TEXT_PROGRAMS = {"echo", "printf", "grep", "egrep", "fgrep", "rg", "ag", "ack", "locate", "man", "which", "type", "gh", "jj", "less",
                 "cat", "head", "tail", "wc", "ls", "mkdir", "touch", "rm", "cp", "mv", "brew", "test", "["}
# The options that run the words after them, as in find -exec and fd -x. The short ones of fd mean other things
# for other programs, as in pytest -x.
EXEC_OPTIONS = {"-exec", "-execdir", "-ok", "-okdir", "--exec", "--exec-batch"}
FD_EXEC_OPTIONS = {"-x", "-X"}
# The options of those programs whose value is the next word, as in uv run --project "$P".
RUNNER_VALUE_OPTIONS = {"--project", "--directory", "--python", "-p", "--with", "--with-requirements",
                        "--with-editable", "--package", "--env-file", "--index", "--default-index", "--extra-index-url",
                        "--from", "--group", "--extra", "--cache-dir", "--config-file", "-u", "-g", "-C", "-n",
                        "-s", "-k", "--signal", "--kill-after", "-o", "--environment",
                        "--manifest-path"}
# The programs that run the program after them, as in uv run bash.
RUNNERS = {"uv", "uvx", "npx", "poetry", "pipenv", "pixi", "conda", "arch", "nice", "nohup", "stdbuf", "caffeinate",
           "time", "sudo", "doas", "env", "timeout", "xcrun", "find", "fd", "strace", "command", "exec", "xargs"}
# The options whose value is a pattern or a name, as in find -name git or uv run --with git.
PATTERN_OPTIONS = {"-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-regex", "-iregex",
                   "-lname", "-ilname", "--with", "--from", "-o", "--exclude", "--include"}
# The aliases of the shell that the line defines, by name.
SHELL_ALIASES: Dict[str, str] = {}

# The builtins of the shell that set variables, as export does.
DECLARES = {"export", "declare", "typeset", "readonly", "local"}

# The options of git that come before the command and take a value.
GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}

# The short options of git commit that take a value. In a cluster such as -am, the rest of the cluster after one of
# them is its value.
COMMIT_VALUE_FLAGS = set("mFCctSu")

SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "|&", ";;", "{", "}"}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\+?=")
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


# The commands of the current call that need the person: a skip lets a tree through without a record.
ASKS: List[str] = []
RECORD_SCRIPT = "record_result.py"
# The variables that tell the record script which harness runs it, and where the transcripts of Codex are.
HARNESS_VARIABLES = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "CODEX_HOME")


def recipe_is(word: str, name: str) -> bool:
    return word == name or word.endswith("::" + name)


# An option of `just --help` with its values, such as `  -f, --justfile <JUSTFILE>` or `--set <VARIABLE> <VALUE>`.
JUST_OPTION = re.compile(r"^\s+(?:-(\w), )?(--[\w-]+)((?: <[^>]+>(?:\.\.\.)?)+)", re.M)


@functools.lru_cache(maxsize=None)
def just_options() -> Optional[Dict[str, int]]:
    """The options of the installed just that take values, with the number of values, from `just --help`. A list
    of values, such as `--command <COMMAND>...`, gives -1: the line runs no recipe. None when just does not run."""
    try:
        run = subprocess.run(["just", "--help"], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    found: Dict[str, int] = {}
    for short, long, values in JUST_OPTION.findall(run.stdout):
        count = -1 if values.endswith("...") else values.count("<")
        found[long] = count
        if short:
            found["-" + short] = count
    # An option of the section Commands, such as --list or --dump, runs no recipe of the line.
    commands = run.stdout.split("Commands:", 1)[1] if "Commands:" in run.stdout else ""
    commands = re.split(r"\n\S", commands, maxsplit=1)[0]
    for short, long in re.findall(r"^\s+(?:-(\w), )?(--[\w-]+)", commands, re.M):
        found[long] = -1
        if short:
            found["-" + short] = -1
    return found or None


def first_recipe(args: List[str], options: Dict[str, int]) -> Optional[str]:
    """The first recipe of a just command line, after its options and its NAME=VALUE overrides, or None."""
    index = 0
    while index < len(args):
        word = args[index]
        index += 1
        if word.startswith("--"):
            count = 0 if "=" in word else options.get(word, 0)
        elif word.startswith("-") and len(word) > 1:
            # A group of short options, such as -vf FILE or -fFILE: the first one that takes a value ends it.
            count = 0
            for position, letter in enumerate(word[1:], start=1):
                if "-" + letter in options:
                    count = options["-" + letter] if position == len(word) - 1 else 0
                    break
        elif "=" in word:
            continue
        else:
            return word
        if count < 0:
            return None
        index += count
    return None


def runs_record(args: List[str]) -> bool:
    """True when a just command line runs the recipe `record`. Without the options of just, any word `record`
    counts, so that no option hides it."""
    options = just_options()
    if options is None:
        return any(recipe_is(word, "record") for word in args)
    first = first_recipe(args, options)
    return bool(first) and recipe_is(first, "record")


def record_calls(rest: List[str]) -> List[str]:
    """The record commands that REST runs: `hook`, `record` or `skip`, from just or from the script. A skip counts in
    any place on the line, so that no spelling of the options hides it."""
    calls = []
    if name_of(rest[0]) == "just":
        calls += ["skip" for word in rest[1:] if recipe_is(word, "record-skip")]
        if runs_record(rest[1:]):
            calls.append("record")
    for index, word in enumerate(rest):
        if posixpath.basename(word) == RECORD_SCRIPT and index + 1 < len(rest):
            calls.append(rest[index + 1])
    return calls


def clears_variables(words: List[str], rest: List[str], command: str) -> bool:
    """True when the line can clear the variables of the harness without their names: the record command runs
    under env or exec, or a part of the line runs unset or export -n."""
    if any(name_of(word) in ("env", "exec") for word in words[:len(words) - len(rest)]):
        return True
    for segment in segments(command):
        program = program_of(segment)
        if program and (name_of(program[0]) == "unset"
                        or name_of(program[0]) == "export" and any(w.startswith("-") and "n" in w for w in program)):
            return True
    return False


def check_records(words: List[str], rest: List[str], command: str) -> None:
    """Stop the record commands that would let an agent write its own record, and note a skip for a question."""
    calls = record_calls(rest)
    if not calls:
        return
    if "hook" in calls:
        raise Blocked("only the SubagentStop hook of the harness runs record_result.py hook")
    # env and exec -c can clear the variables without naming them, and unset can name them through a pattern.
    if any(name in command for name in HARNESS_VARIABLES) or clears_variables(words, rest, command):
        raise Blocked("a record command with env, exec, unset or a change of " + ", ".join(HARNESS_VARIABLES) +
                      " could write a record that no fresh agent gave")
    if "record" in calls and os.environ.get("JN_HOOK_HARNESS") == "claude":
        raise Blocked("in Claude Code the SubagentStop hook writes the records; give the packet to a fresh agent")
    if "skip" in calls:
        ASKS.append(" ".join(rest))


def reads_as_shell(words: List[str]) -> bool:
    """True when the program WORDS reads its input as shell: a shell, also after a program that runs it, as in
    `uv run bash`, or a program that the shell names, as in "$SHELL". A program such as gh or cat does not."""
    if name_of(words[0]) in TEXT_PROGRAMS:
        return False
    if any(name_of(word) in SHELLS for word in words) or OPAQUE.search(last_part(words[0])):
        return True
    # After a program that runs another, as in `uv run $SH` or `stdbuf -oL $SH`, the program that the shell names may
    # be a shell. The value of an option that takes one, as in `uv run --project "$P" python`, is not the program.
    # Any other option may take no value, as in `uv run --no-sync "$SHELL"`.
    return name_of(words[0]) in RUNNERS and any(
        OPAQUE.search(last_part(word)) and words[index - 1] not in RUNNER_VALUE_OPTIONS
        for index, word in enumerate(words) if index)


def continues(line: str, quote: Nesting = None) -> bool:
    """True when LINE, with QUOTE open at its start, goes on in the next line: it ends with an odd number of
    backslashes, outside a comment and outside ' and $'. A \\ at the end is a backslash, and a backslash in a
    comment, as in `ls # note \\`, does not join the lines."""
    end, comment = scan_quotes(line, quote)
    if comment is not None or end and end[-1] in ("'", "$'"):
        return False
    return (len(line) - len(line.rstrip("\\"))) % 2 == 1


def pipe_parts(text: str) -> List[str]:
    """The parts of TEXT between the | and |& outside quotes, up to the first ;, &&, || or & outside quotes, which
    ends the command."""
    parts, current, quote, index = [], "", None, 0
    # The open $( ${ and $(( of the text, and a backtick, whose separators belong to them.
    nested: List[str] = []
    while index < len(text):
        char = text[index]
        if quote is None and (text.startswith(("$(", "${"), index) or char == "`" and nested[-1:] != ["`"]):
            nested.append("`" if char == "`" else text[index + 1])
            current += text[index:index + (1 if char == "`" else 2)]
            index += 1 if char == "`" else 2
            continue
        if quote is None and nested and char == {"(": ")", "{": "}", "`": "`"}[nested[-1]]:
            nested.pop()
            current += char
            index += 1
            continue
        if quote is None and nested and char == "(" and nested[-1] == "(":
            nested.append("(")
            current += char
            index += 1
            continue
        if quote is None and nested and char not in "'\"\\" and not text.startswith("$'", index):
            current += char
            index += 1
            continue
        if quote == "$'" and char == "\\":
            current += text[index:index + 2]
            index += 2
            continue
        if quote is None and text.startswith("$'", index):
            # An ANSI-C quote, in which a backslash takes the next character.
            quote = "$'"
            current += "$'"
            index += 2
            continue
        if quote == "$'":
            quote = None if char == "'" else quote
            current += char
            index += 1
            continue
        if quote == '"' and char == "\\":
            current += text[index:index + 2]
            index += 2
            continue
        if quote:
            quote = None if char == quote else quote
            current += char
        elif char == "\\":
            current += text[index:index + 2]
            index += 2
            continue
        elif char in "'\"":
            quote = char
            current += char
        elif char == ";" or text.startswith(("&&", "||"), index) or char == "&" and not current.endswith(
                ("|", ">", "<")) and not text.startswith("&>", index):
            # A & of a redirection, as in 2>&1 or &>file, does not end the command.
            break
        elif char == "|":
            parts.append(current)
            current = ""
            if text.startswith("|&", index):
                index += 1
        else:
            current += char
        index += 1
    return parts + [current]


def heredoc_runs(line: str) -> bool:
    """True when a shell runs the body of the first here-doc of LINE: its reader, before or after the here-doc
    word, as in `bash <<EOF` or `<<EOF bash`, or a command after a | of the same command, as in `cat <<EOF |
    bash`. A line that ends with a | could pipe the body into a command after it, so its body counts as shell."""
    found = next((m for m in HEREDOC.finditer(line) if outside_quotes(line, m.start())), None)
    if not found:
        return False
    # A case in a $(...), as in $(case x in a) true;; esac), has a ) and a ;; that end nothing.
    if any(not quoted(line, match.start()) and set(scan_quotes(line[:match.start()])[0] or ()) & {"$(", "(", "`"}
           for match in re.finditer(r"(?:^|(?<=[\s;&|(]))case\s+\S+\s+in\b", line) if match.start() > found.start()):
        return True
    before = segments(line[:found.start()])
    after = segments(line[found.end():])
    words = program_of((before[-1] if before else []) + (after[0] if after else []))
    runs = bool(words) and reads_as_shell(words)
    for part in pipe_parts(line[found.end():])[1:]:
        piped = program_of((segments(part) or [[]])[0])
        runs = runs or bool(piped) and reads_as_shell(piped)
    return runs or line.rstrip().endswith(("|", "|&"))


def without_heredocs(command: str) -> Tuple[str, List[str]]:
    """The command with the body of each here-doc taken out and each line end made a `;`, and the bodies that a
    shell runs, such as the body of `bash <<EOF`. A line that ends with a backslash goes on. A line end inside
    quotes stays in the quoted word. A comment is dropped, so an apostrophe in it is not a quote."""
    kept: List[str] = []
    bodies: List[str] = []
    end: Optional[str] = None
    body: List[str] = []
    runs = False
    # The text of a here-doc line so far, while it ends with a backslash and goes on in the next line. The body
    # starts after the line that does not.
    joined: Optional[str] = None
    # The quote that is open at the start of the line, from the lines before it.
    state: Nesting = None
    for line in command.split("\n"):
        if joined is not None:
            kept.append(line)
            goes_on = continues(line, state)
            state = scan_quotes(line, state)[0]
            joined += line[:-1] if goes_on else line
            if not goes_on:
                runs, joined = heredoc_runs(joined), None
            continue
        if end is not None:
            if line.strip() == end:
                if runs:
                    bodies.append("\n".join(body))
                end = None
            else:
                body.append(line)
            continue
        kept.append(line)
        start, state = state, scan_quotes(line, state)[0]
        found = next((m for m in HEREDOC.finditer(line) if outside_quotes(line, m.start(), start)), None)
        if found and "((" not in line[:found.start()]:
            end, body = found.group(2), []
            if continues(line, start):
                joined = line[:-1]
            else:
                runs = heredoc_runs(line)
    if end is not None and runs:
        bodies.append("\n".join(body))
    # The command text: each line without its comment, a line that goes on joined with the next, and each line end
    # outside quotes as a `;`. The quotes come from scan_quotes, as everywhere in the guard.
    text, state = "", None
    for line in kept:
        goes_on = continues(line, state)
        after, comment = scan_quotes(line, state)
        if comment is not None:
            line = line[:comment]
        if goes_on:
            text += line[:-1]
        else:
            text += line + (" ; " if after is None else "\n")
        state = after
    return text, bodies


# The open quotes and substitutions at a place of a shell line, innermost last: ', ", $', $(, ( and `.
Nesting = Optional[Tuple[str, ...]]


def closing(text: str, start: int) -> int:
    """The place after the ) or the backtick that closes the $( or the backtick at START of TEXT, with the quotes
    inside it, as in $(echo ')'). The end of TEXT when nothing closes it."""
    end = scan_quotes(text[start:], until_closed=True)[1]
    return len(text) if end is None else start + end


def scan_quotes(text: str, quote: Nesting = None, until_closed: bool = False) -> Tuple[Nesting, Optional[int]]:
    """The quotes and substitutions that are open at the end of TEXT, when QUOTE is open at its start, or None, and
    the place of the # that starts a comment, or None. In $'...' and in "...", a backslash takes the next
    character. In "...", a $(...) or a backtick holds a line of its own, with its own quotes. A # starts a comment
    only at the start of a word, and not after an escaped character, as in \\;#. With UNTIL_CLOSED, the place
    after the end of the first quote or substitution comes in place of the comment."""
    stack = list(quote or ())
    index, escaped = 0, False
    while index < len(text):
        char, top = text[index], stack[-1] if stack else None
        if top == "'":
            if char == "'":
                stack.pop()
        elif char == "\\" and top != "'":
            index, escaped = index + 2, True
            continue
        elif top == "$'":
            if char == "'":
                stack.pop()
        elif top == '"':
            if text.startswith("$(", index):
                stack.append("$(")
                index += 2
                continue
            if char == "`":
                stack.append("`")
            elif char == '"':
                stack.pop()
        elif text.startswith("$'", index):
            stack.append("$'")
            index += 2
            continue
        elif text.startswith("$(", index):
            stack.append("$(")
            index += 2
            continue
        elif char == "(" and top in ("$(", "("):
            stack.append("(")
        elif char == ")" and top in ("$(", "("):
            stack.pop()
        elif char == "`":
            if top == "`":
                stack.pop()
            else:
                stack.append("`")
        elif char in "'\"":
            stack.append(char)
        elif char == "#" and top is None and not escaped and (index == 0 or text[index - 1] in " \t\n;&|()"):
            return None, index
        escaped = False
        index += 1
        if until_closed and not stack:
            return None, index
    return (tuple(stack) or None), None


def quoted(line: str, position: int) -> bool:
    """True when POSITION of LINE is in a quote or a comment. A $(...) outside quotes is not a quote."""
    stack, comment = scan_quotes(line[:position])
    return comment is not None or any(part in ("'", '"', "$'") for part in stack or ())


def outside_quotes(line: str, position: int, quote: Nesting = None) -> bool:
    """True when POSITION of LINE is outside quotes and comments, so that a `<<` in a message is not a here-doc.
    QUOTE is the quote that is open at the start of LINE."""
    return scan_quotes(line[:position], quote) == (None, None)


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
            j = closing(command, i)
            inner.append(command[i + 2:j - 1])
            out.append(SUBSTITUTION.format(len(inner) - 1))
            i = j
            continue
        if quote != "'" and char == "`":
            j = closing(command, i)
            inner.append(command[i + 1:j - 1])
            out.append(SUBSTITUTION.format(len(inner) - 1))
            i = j
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
    lexer = shlex.shlex(plain_ansi(command), posix=True, punctuation_chars=";&|()<>")
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


def alias_of(name: str, cwd: str, defined: Dict[str, str], place: Sequence[str] = (),
             env: Optional[Dict[str, str]] = None) -> Optional[str]:
    """The text of the git alias NAME, from `git -c` or from the config, or None. PLACE and ENV are the options and
    the variables of the command, which choose the repository and the config files."""
    if name in defined:
        return defined[name]
    try:
        run = subprocess.run(["git", *place, "config", "--get", f"alias.{name}"], cwd=cwd or None,
                             env={**os.environ, **(env or {})}, stdin=subprocess.DEVNULL, capture_output=True,
                             text=True, timeout=5)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return run.stdout.strip() if run.returncode == 0 and run.stdout.strip() else None


# An ANSI-C quote, $'...', which shlex does not know.
ANSI_QUOTE = re.compile(r"\$'(?:[^'\\]|\\.)*'")


ANSI_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f",
                "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}


def ansi_value(body: str) -> str:
    """The value of the ANSI-C quote $'BODY', as bash gives it: \\n, \\xHH, \\NNN, \\uHHHH and the others."""
    def one(match) -> str:
        code = match.group(1)
        if code[0] in ANSI_ESCAPES and len(code) == 1:
            return ANSI_ESCAPES[code]
        if code[0] in "xuU":
            value = int(code[1:], 16) if code[1:] else -1
            return chr(value) if 0 <= value <= 0x10FFFF else match.group(0)
        if code[0] == "c":
            return chr(ord(code[1:2] or "@") & 31)
        if code.isdigit() and set(code) <= set("01234567"):
            return chr(int(code, 8) & 255)
        # bash keeps an escape that it does not know, as in \z.
        return match.group(0)
    # bash ends the word at a NUL, as in $'--no-verify\0x'.
    return re.sub(r"\\(x[0-9A-Fa-f]{0,2}|u[0-9A-Fa-f]{0,4}|U[0-9A-Fa-f]{0,8}|[0-7]{1,3}|c.?|.)", one, body).split(
        "\0", 1)[0]


def plain_ansi(text: str) -> str:
    """TEXT with each $'...' outside other quotes as a plain quoted word of its value, which shlex can read."""
    out, index, quote = [], 0, None
    while index < len(text):
        char = text[index]
        if quote is None and char == "\\":
            out.append(text[index:index + 2])
            index += 2
            continue
        if quote is None and text.startswith("$'", index):
            match = ANSI_QUOTE.match(text, index)
            if match:
                out.append(shlex.quote(ansi_value(match.group(0)[2:-1])))
                index = match.end()
                continue
        if quote == '"' and char == "\\":
            out.append(text[index:index + 2])
            index += 2
            continue
        if quote is None and char in "'\"":
            quote = char
        elif quote is not None and char == quote:
            quote = None
        out.append(char)
        index += 1
    return "".join(out)


def split(text: str) -> List[str]:
    text = plain_ansi(text)
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


# The variables that change which config files git reads, or which repository it is in.
CONFIG_VARIABLES = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_COUNT",
                    "GIT_CONFIG_PARAMETERS", "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "HOME", "XDG_CONFIG_HOME")


def hooks_path_set(cwd: str, place: List[str], env: Dict[str, str]) -> Optional[str]:
    """Where git, in CWD with the options PLACE such as -C and the variables ENV, has a core.hooksPath: a config
    file, an include, config.worktree or a variable. None when it has none. Then git runs the hooks of that folder
    and not the commit gate. An empty value also turns the hooks off. When git cannot answer, the guard cannot know,
    and the text starts with ? and names the reason."""
    for name, value in env.items():
        if (name in CONFIG_VARIABLES or name.startswith("GIT_CONFIG")) and "$" in value:
            return f"?the variable {name}, whose value the guard cannot know"
    if any("$" in option for option in place):
        return "?an option of git whose value the guard cannot know"
    # The folder may not exist yet, as after `git init new && cd new`. A new repository has no hooksPath of its
    # own, so the config of the nearest folder that exists, without the options that name the repository, holds
    # each one that it can have.
    folder, index = cwd or os.getcwd(), 0
    while index < len(place):
        if place[index] == "-C":
            folder = os.path.join(folder, place[index + 1])
        index += 2 if place[index] in ("-C", "-c", "--git-dir", "--work-tree") else 1
    if not os.path.isdir(folder):
        while folder and not os.path.isdir(folder):
            folder = os.path.dirname(folder)
        cwd, kept, index = folder, [], 0
        while index < len(place):
            step = 2 if place[index] in ("-C", "-c", "--git-dir", "--work-tree") else 1
            if place[index] == "-c" or place[index].startswith("--config-env="):
                kept += place[index:index + step]
            index += step
        place = kept
    try:
        run = subprocess.run(["git", *place, "config", "--show-origin", "--get-all", "core.hooksPath"],
                             cwd=cwd or None, env={**os.environ, **env}, stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=5)
    except (OSError, ValueError, subprocess.SubprocessError):
        return "?a repository or a config that the guard cannot read"
    if run.returncode == 1:
        return None
    if run.returncode != 0:
        return "?a repository or a config that the guard cannot read"
    return run.stdout.split("\t", 1)[0].strip() or "the config of git"


# For git commit, merge and pull: the short options whose value is the next word, the short options whose value
# can only be the rest of the word, and the long options whose value is the next word. A message or a file name
# may hold a $.
VALUE_OPTIONS = {
    "commit": (set("mFCct"), set("Su"), {"--message", "--file", "--reuse-message", "--reedit-message", "--fixup",
                                         "--squash", "--author", "--date", "--trailer", "--template", "--cleanup",
                                         "--pathspec-from-file"}),
    "merge": (set("mFsX"), set("S"), {"--message", "--file", "--strategy", "--strategy-option", "--into-name",
                                      "--cleanup"}),
    "pull": (set("sX"), set("S"), {"--strategy", "--strategy-option", "--depth", "--deepen", "--shallow-since",
                                   "--shallow-exclude", "--upload-pack"}),
}
# A word that the shell changes in a way that the guard does not follow: a $, a backtick, a list in braces or a
# pattern of file names.
OPAQUE = re.compile(r"[$`*?[]|\{[^}]*,[^}]*\}")


def shown(word: str) -> str:
    """WORD as the person wrote it, with $(...) in place of the mark of a substitution."""
    return re.sub(r"\$__substitution\d+__", "$(...)", word)


def opaque_option(args: Sequence[str], name: str = "commit") -> Optional[str]:
    """The first word of ARGS, the words after git NAME, that the shell could turn into an option such as
    --no-verify, or None. NAME is commit, merge or pull. The values of the options, and the words after --, are
    left out."""
    next_flags, rest_flags, next_options = VALUE_OPTIONS[name]
    skip = False
    for word in args:
        if skip:
            skip = False
            continue
        if word == "--":
            return None
        if word.startswith("--"):
            option = word.split("=", 1)[0]
            if OPAQUE.search(option):
                return word
            skip = "=" not in word and option in next_options
            continue
        if word.startswith("-") and len(word) > 1:
            for index, flag in enumerate(word[1:], start=1):
                if OPAQUE.search(flag):
                    return word
                if flag in next_flags or flag in rest_flags:
                    skip = index == len(word) - 1 and flag in next_flags
                    break
            continue
        if OPAQUE.search(word):
            return word
    return None


def check_git(args: List[str], cwd: str, depth: int = 0, env: Optional[Dict[str, str]] = None,
              lost: bool = False, bare: Optional[Dict[str, str]] = None, scanned: bool = False) -> None:
    """Stop the git command ARGS that goes around the gate. ENV holds the variables of the command. BARE holds only
    the assignments in front of git, because the shell may not export the others. LOST is true when the folder of
    the command is not known, after a cd to a word that the guard cannot know."""
    rest = list(args)
    env = env or {}
    bare = env if bare is None else bare
    aliases: Dict[str, str] = {}
    # The options that choose the repository, which the check of core.hooksPath must also use.
    place: List[str] = []
    while rest and rest[0].startswith("-"):
        option = rest.pop(0)
        value = None
        if option in GIT_VALUE_OPTIONS and rest:
            value = rest.pop(0)
            if option in ("-C", "--git-dir", "--work-tree"):
                place += [option, value]
        elif option.startswith(("--git-dir=", "--work-tree=")):
            place.append(option)
        elif option.startswith("-c") and len(option) > 2:
            option, value = "-c", option[2:]
        elif option.startswith("--config-env="):
            option, value = "--config-env", option.split("=", 1)[1]
        if option in ("-c", "--config-env") and value:
            # A setting such as include.path can also bring in a core.hooksPath.
            place += ["-c", value] if option == "-c" else [f"--config-env={value}"]
            if sets_hooks_path(value):
                raise Blocked("core.hooksPath moves the git hooks, and the commit gate with them. Leave it alone")
            if value.lower().startswith("alias.") and "=" in value:
                key, text = value[len("alias."):].split("=", 1)
                aliases[key] = text
    if not rest:
        return
    name, sub = rest[0], rest[1:]
    # A git found after another program may be only a word, such as the pattern of find -name.
    if OPAQUE.search(name) and not scanned:
        raise Blocked(f"the git command `{shown(name)}` is a word that the shell changes, so the guard cannot check "
                      "it. Write the command plainly")
    if name in ("commit", "merge", "pull") and opaque_option(sub, name):
        raise Blocked(f"the word `{shown(opaque_option(sub, name))}` of `git {name}` could become an option such as "
                      "--no-verify, so the guard cannot check it. Write it plainly, or put it after --")
    if name == "commit" and commit_skips_hooks(sub):
        raise Blocked("`git commit --no-verify` skips the commit gate. Commit without it, and run the target or the "
                      "step that the gate names")
    if name in ("merge", "pull") and has_abbreviation(sub, "--no-verify", "--no-veri"):
        raise Blocked(f"`git {name} --no-verify` skips the gate of the merge. Merge without it")
    if name in ("commit-tree", "update-ref"):
        raise Blocked(f"`git {name}` makes a commit or moves a branch around the commit gate. Use `git commit`")
    if name in ("commit", "merge", "pull"):
        # The shell may or may not export a variable, so git is asked both ways.
        origin = "?a folder that the guard cannot know" if lost else (
            hooks_path_set(cwd, place, env) or (hooks_path_set(cwd, place, bare) if bare != env else None))
        if origin and origin.startswith("?"):
            raise Blocked(f"the guard cannot check core.hooksPath, because of {origin[1:]}. Then git might not run "
                          "the commit gate. Write the command with plain values")
        if origin:
            raise Blocked(f"core.hooksPath is set, in {origin}, so git would not run the commit gate. Ask the person "
                          "to remove it there. A hooks folder of their own can call the pre-commit hook of the gate")
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
    if name == "submodule" and "foreach" in sub:
        # The command of foreach runs in each submodule: one word through sh -c, more words as they are.
        words = sub[sub.index("foreach") + 1:]
        while words and words[0] in ("--recursive", "-q", "--quiet"):
            words = words[1:]
        check_command(words[0] if len(words) == 1 else shlex.join(words), cwd, known=env)
    if name == "rebase":
        for index, word in enumerate(sub):
            if word in ("-x", "--exec") and index + 1 < len(sub):
                check_command(sub[index + 1], cwd, known=env)
            elif word.startswith("--exec="):
                check_command(word.split("=", 1)[1], cwd, known=env)
    if depth < 3 and name not in ("commit", "merge", "pull", "config", "rebase"):
        expanded = alias_of(name, cwd, aliases, place, env)
        if expanded and expanded.startswith("!"):
            check_command(expanded[1:] + " " + shlex.join(sub), cwd, depth + 1, env)
        elif expanded:
            check_git(place + split(expanded) + sub, cwd, depth + 1, env, lost, bare, scanned)


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
    # The transcripts of Codex are the proof of a `just record` in Codex.
    codex = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    found.append(("the Codex sessions folder", os.path.join(os.path.realpath(codex), "sessions")))
    if common:
        found.append((".git/hooks", os.path.join(common, "hooks")))
        # A core.hooksPath written into the config moves the hooks, and the commit gate with them.
        found.append((".git/config", os.path.join(common, "config")))
        if os.path.basename(common) == ".git":
            # The main checkout holds the shared log, and its settings decide whether the records come from a hook.
            found += [(path, os.path.join(os.path.dirname(common), path)) for path in PROTECTED]
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
    if (word == "~" or word.startswith("~/")) and "HOME" in known:
        word = known["HOME"] + word[1:]

    def value(match) -> str:
        name = match.group(1) or match.group(2)
        filled = FILLED.match(name)
        if filled and int(filled.group(1)) < len(inner):
            found = rev_parse_value(inner[int(filled.group(1))], here) if here else None
            return found if found is not None else match.group(0)
        return known.get(name, match.group(0))

    return VARIABLE.sub(value, word)


# The start of a function: `name() {` or `function name`.
FUNCTION = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\s*\(\s*\)\s*\{|\bfunction\s+[A-Za-z_]")
CONFIG_NAME = re.compile(r"^GIT_CONFIG[A-Z0-9_]*$")


def spread_split_string(words: List[str]) -> List[str]:
    """WORDS with the text of each -S of env split into words, as env does: -S TEXT, -STEXT, -vS TEXT, -iSTEXT and
    --split-string=TEXT. Only the options of env count. A cluster stops at -u or -C, whose value is the rest."""
    spread: List[str] = []
    options = pending = text_next = False
    for word in words:
        if text_next:
            spread += split(word)
            text_next = False
        elif not options:
            spread.append(word)
            options = name_of(word) == "env"
        elif pending:
            spread.append(word)
            pending = False
        elif word.startswith("--split-string="):
            spread += split(word.split("=", 1)[1])
        elif word == "--split-string":
            text_next = True
        elif word.startswith("--"):
            spread.append(word)
            pending = word in ("--unset", "--chdir")
        elif word.startswith("-") and len(word) > 1:
            for index, flag in enumerate(word[1:], start=1):
                if flag in "uC":
                    spread.append(word)
                    pending = index == len(word) - 1
                    break
                if flag == "S":
                    spread += [word[:index]] if index > 1 else []
                    if word[index + 1:]:
                        spread += split(word[index + 1:])
                    else:
                        text_next = True
                    break
            else:
                spread.append(word)
        else:
            spread.append(word)
            options = name_of(word) == "env" or ASSIGNMENT.match(word) is not None
    return spread


def last_part(word: str) -> str:
    """The part of WORD after its last / outside a ${...}, as in ${X:-/usr/bin/git}, which is all of it."""
    depth, cut = 0, -1
    for index, char in enumerate(word):
        if word.startswith("${", index):
            depth += 1
        elif char == "}" and depth:
            depth -= 1
        elif char == "/" and not depth:
            cut = index
    return word[cut + 1:]


def could_be_git(program: str, inner: List[str]) -> bool:
    """True when PROGRAM, a word whose last path part the shell changes, could be git: its substitution names git,
    its default, as in ${X:-git} or ${X-/usr/bin/git}, is git, or its pattern matches git."""
    last = last_part(program)
    for default in re.findall(r"\$\{[A-Za-z_][A-Za-z0-9_]*:?[-=+]([^}]*)\}", last):
        if name_of(default.strip("'\"")) == "git":
            return True
    for number in re.findall(r"__substitution(\d+)__", last):
        if int(number) < len(inner) and re.search(r"\bgit\b", inner[int(number)]):
            return True
    return "$" not in last and "`" not in last and fnmatch.fnmatchcase("git", last)


# The options of a shell whose value is the next word.
SHELL_VALUE_OPTIONS = {"-o", "+o", "-O", "+O", "--rcfile", "--init-file"}


def shell_text(words: List[str]) -> Optional[str]:
    """The command text of the shell words WORDS, without the program. A shell reads its options up to the first
    word that is not one, or up to --. When a short cluster held c, as in `bash -e -c TEXT` or `bash -c -x TEXT`,
    that word is the text. None when no cluster held c, as in `bash script.sh -c x`."""
    index, seen = 0, False
    while index < len(words):
        word = words[index]
        if word == "--":
            index += 1
            break
        if word in SHELL_VALUE_OPTIONS:
            index += 2
            continue
        if not word.startswith(("-", "+")) or word in ("-", "+"):
            break
        if not word.startswith("--") and "c" in word[1:]:
            seen = True
        # In a cluster such as -oc errexit, each o or O takes the next word.
        index += 1 + (0 if word.startswith("--") else word[1:].count("o") + word[1:].count("O"))
    return words[index] if seen and index < len(words) else None


def assign(variables: Dict[str, str], word: str) -> None:
    """Put the assignment WORD, such as A=1 or A+=1, into VARIABLES."""
    name, value = word.split("=", 1)
    if name.endswith("+"):
        name = name[:-1]
        value = variables.get(name, "") + value
    variables[name] = value


def check_command(command: str, cwd: str, depth: int = 0, known: Optional[Dict[str, str]] = None) -> None:
    """Stop the shell line COMMAND, run in CWD, when it goes around the gate. KNOWN holds the variables that an outer
    command gives it, such as the exports in front of `bash -c`."""
    if depth > 4:
        if re.search(r"\bgit\b", command):
            raise Blocked("the git command is nested too deeply for the guard to check. Write it more plainly")
        return
    outer = dict(known or {})
    command, bodies = without_heredocs(command)
    command, inner = substitutions(command)
    # A substitution or a here-doc may run after any assignment of the line, so it gets them all.
    every = dict(outer)
    for words in segments(command):
        for word in words:
            if ASSIGNMENT.match(word):
                assign(every, word)
    # An alias of the shell, from `alias NAME=TEXT`, runs TEXT.
    for words in segments(command):
        if words[:1] == ["alias"]:
            for word in words[1:]:
                if "=" in word:
                    key, text = word.split("=", 1)
                    SHELL_ALIASES[key] = text
    for text in inner + bodies:
        check_command(text, cwd, depth + 1, every)
    here, before = cwd, cwd
    known = {name: os.environ[name] for name in KNOWN_VARIABLES if os.environ.get(name)}
    # The body of a function runs with the assignments of each call, so a line that defines one starts with them all.
    known.update(every if FUNCTION.search(command) else outer)
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
        # env -S splits its text into the program and its words.
        if any(name_of(w) == "env" for w in words):
            words = spread_split_string(words)
        # read, printf -v, for, mapfile and getopts set a variable from a word that the guard does not follow.
        if words and name_of(words[0]) != "git":
            for word in words:
                if word in CONFIG_VARIABLES or CONFIG_NAME.match(word):
                    known[word] = "$unknown"
        # A GIT_CONFIG_ variable can set core.hooksPath for every later git command, also through export.
        settings = [w for w in words if ASSIGNMENT.match(w) and w.upper().startswith("GIT_CONFIG")]
        if any("hookspath" in w.lower() for w in settings):
            raise Blocked("core.hooksPath moves the git hooks, and the commit gate with them. Leave it alone")
        rest = program_of(words)
        if not rest or rest[0] in DECLARES:
            for word in (rest[1:] if rest else words):
                if ASSIGNMENT.match(word):
                    assign(known, word)
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
        check_records(words, rest, command)
        program = name_of(rest[0])
        # A here-string, as in bash <<<TEXT, gives TEXT to the program as its input.
        if "<<<" in words[:-1] and reads_as_shell(rest):
            for index, word in enumerate(words[:-1]):
                if word == "<<<":
                    check_command(words[index + 1], here or cwd, depth + 1, known)
        # The variables of the shell, and the assignments in front of the program, also after env.
        env = {k: v for k, v in known.items() if k != "PWD"}
        prefix = words[:len(words) - len(rest)]
        for word in prefix:
            if ASSIGNMENT.match(word):
                assign(env, word)
        # xargs adds words from its input, which the guard does not see.
        if program == "git" and any(name_of(w) in ("xargs", "parallel") for w in prefix) and (
                len(rest) == 1 or any(w in ("commit", "merge", "pull") for w in rest)):
            raise Blocked("xargs adds words to the git command that the guard cannot see. Run git directly")
        # A known variable with spaces, such as X='git commit -n' and then $X, is split by the shell.
        if " " in rest[0]:
            check_command(rest[0] + " " + shlex.join(rest[1:]), here or cwd, depth + 1, env)
        bare = {}
        for word in prefix:
            if ASSIGNMENT.match(word):
                assign(bare, word)
        # A program whose last path part the shell changes could be git or a shell. One such as $VENV/bin/python
        # has a plain name, and goes on as that program.
        if OPAQUE.search(last_part(rest[0])):
            if could_be_git(rest[0], inner):
                raise Blocked(f"the program `{shown(rest[0])}` is a word that the shell changes, so the guard "
                              "cannot check the git command. Write git plainly")
            if shell_text(rest[1:]) is not None:
                check_command(shell_text(rest[1:]), here or cwd, depth + 1, env)
            # Its words get the checks of git, such as those of commit -n, config and rebase -x. It could also be a
            # program that runs git, such as $UV run git.
            check_git(rest[1:], here or cwd, env=env, lost=here == "", bare=bare, scanned=True)
            scan_wrapped(rest, here or cwd, depth, env, here == "", bare)
            continue
        if program in SHELL_ALIASES:
            # The shell does not expand an alias inside its own text again.
            text = SHELL_ALIASES.pop(program)
            try:
                check_command(text + " " + shlex.join(rest[1:]), here or cwd, depth + 1, env)
            finally:
                SHELL_ALIASES[program] = text
            continue
        if program == "git":
            check_git(rest[1:], here or cwd, env=env, lost=here == "", bare=bare)
        elif program == "eval":
            check_command(" ".join(rest[1:]), here or cwd, depth + 1, env)
        elif program in SHELLS:
            if shell_text(rest[1:]) is not None:
                check_command(shell_text(rest[1:]), here or cwd, depth + 1, env)
        elif program not in TEXT_PROGRAMS:
            scan_wrapped(rest, here or cwd, depth, env, here == "", bare)


def scan_wrapped(rest: List[str], cwd: str, depth: int, env: Dict[str, str], lost: bool,
                 bare: Dict[str, str]) -> None:
    """Check each git word and each shell -c after the program REST[0], as in find -exec, uv run or arch. Any git
    word may be the one that runs. A git that is a pattern, as in find -name git, may be followed by a word that
    the shell changes."""
    for index in range(1, len(rest)):
        if name_of(rest[index]) == "git":
            pattern = rest[index - 1] in PATTERN_OPTIONS
            check_git(rest[index + 1:], cwd, env=env, lost=lost, bare=bare, scanned=pattern)
        elif rest[index - 1] in EXEC_OPTIONS or any(name_of(w) in ("fd", "fdfind") for w in rest[:index]) and \
                rest[index - 1] in FD_EXEC_OPTIONS or \
                rest[index].startswith(("--exec=", "--exec-batch=")):
            # A program that the shell names after find -exec or fd -x, also after a prefix such as env, may be git.
            program = program_of(rest[index:])
            if program and OPAQUE.search(last_part(program[0])):
                check_git(program[1:], cwd, env=env, lost=lost, bare=bare, scanned=True)
        if (name_of(rest[index]) in SHELLS or OPAQUE.search(last_part(rest[index]))) and \
                shell_text(rest[index + 1:]) is not None:
            # A shell, or a program that the shell names, as in uv run $SH -c TEXT.
            check_command(shell_text(rest[index + 1:]), cwd, depth + 1, env)


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
    payload = None
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        cwd = payload.get("cwd")
        cwd = cwd if isinstance(cwd, str) and os.path.isdir(cwd) else os.getcwd()
        check(payload, cwd)
        if ASKS:
            reason = (f"{ASKS[0]} lets the worktree tree through without the record of a fresh agent, and the gate "
                      f"then lets the commit through. Only the person decides that")
            if os.environ.get("JN_HOOK_HARNESS") == "codex":
                raise Blocked(reason + ". Ask the person to run the command")
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                                     "permissionDecisionReason": reason}}))
            return 0
    except Blocked as blocked:
        print(f"gate guard: {blocked}.", file=sys.stderr)
        return 2
    except Exception as error:
        # A fault of the guard lets the call run, because the commit gate still checks. A git line could go around
        # the gate, so it stops.
        tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
        command = command_of(tool_input) if isinstance(tool_input, dict) else None
        # A $'...' can spell git without the word, as in $'\\x67it'.
        if command is not None and (re.search(r"\bgit\b", command) or "$'" in command):
            print(f"gate guard: could not check the git call ({error!r}), so it stops. Write it more plainly",
                  file=sys.stderr)
            return 2
        print(f"gate guard: could not check the call ({error!r}), so it runs", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
