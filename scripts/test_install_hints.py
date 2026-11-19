"""Each install.sh of jlog, jagt and gest comes from the ref of its release, never from a branch.

A hint that takes install.sh from main runs a later install.sh than the release that --tag names. The refs are the
same as in jnterfaces: the tag of the release.
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
# The release that each install line names with --tag.
RELEASES = {
    "jlog": "v0.3.0",
    "jagt": "v0.6.4",
    "gest": "v0.6.0",
}
# The ref of install.sh for each program.
REFS = {
    "jlog": "v0.3.0",
    "jagt": "v0.6.4",
    "gest": "v0.6.0",
}
URL = "curl -fsSL https://raw.githubusercontent.com/rahuldave/{name}/{ref}/scripts/install.sh"
PIPE = " | sh -s -- --tag {tag}"
HINT = URL + PIPE
# Any program of rahuldave before an install.sh, on any host, with any case.
ANY_PROGRAM = re.compile(r"rahuldave/([\w.-]+)/\S*?$", re.IGNORECASE)
# A program that the line names, for an install.sh without the URL of its owner.
PROGRAM_NAME = re.compile(r"\b(jlog|jagt|gest)\b", re.IGNORECASE)
# The tag ends at the end of the line, a space or a mark. So v0.3.0-rc1 and v0.3.0.1 fail.
TAG_END = re.compile(r"(?:$|[\s`\"');<]|[.,](?!\d))")


def pin_problems(line: str, comments: bool = True, before_line: str = "") -> tuple[list[str], set[str]]:
    """Why each install.sh of jlog, jagt or gest on a line is not the exact pinned hint, and the programs it names.
    comments says whether a line that starts with # is a comment, as in YAML, shell and Python, and not a heading of
    Markdown. before_line is the line before, where wrapped prose may name the program."""
    if "install.sh" not in line:
        return [], set()
    problems, programs = [], set()
    if "rahuldave" not in line.lower():
        # A comment of a workflow may tell where install.sh comes from. Prose elsewhere gives the line itself.
        if PROGRAM_NAME.search(before_line + " " + line) and not (comments and line.lstrip().startswith("#")):
            problems.append("an install.sh of a program with no pinned line")
        return problems, programs
    if line.lstrip().startswith("|"):
        # A | inside backticks still ends the cell of a Markdown table, so the hint loses its --tag.
        problems.append("an install line in a Markdown table")
    start = 0
    while (index := line.find("install.sh", start)) >= 0:
        end = index + len("install.sh")
        before, after = line[start:end], line[end:]
        start = end
        found = ANY_PROGRAM.search(before[: -len("/scripts/install.sh")] if before.endswith("/scripts/install.sh") else before)
        if not found:
            problems.append("an install.sh that names no program of rahuldave")
            continue
        name = found.group(1).lower()
        programs.add(name)
        if name not in REFS:
            problems.append(f"no pinned ref for {name}")
            continue
        pipe = PIPE.format(tag=RELEASES[name])
        if not before.endswith(URL.format(name=name, ref=REFS[name])) or not after.startswith(pipe):
            problems.append(f"not the pinned hint of {name}")
            continue
        rest = after[len(pipe):]
        if not TAG_END.match(rest) or "--tag" in re.split(r"[`;|&]", rest)[0]:
            problems.append(f"more after the tag of {name}")
    return problems, programs


def line_problems(lines: list[str], comments: bool = True) -> list[tuple[int, list[str], set[str]]]:
    """The problems of each line. A URL that a line break splits counts as one line with the line before it, and a
    command that ends in a backslash goes on with the next line."""
    results = []
    for number, line in enumerate(lines, 1):
        previous = lines[number - 2] if number > 1 else ""
        if "install.sh" in line and "rahuldave" not in line.lower() and "rahuldave" in previous.lower():
            line = previous.rstrip().rstrip("\\").rstrip() + line.strip()
        if line.rstrip().endswith("\\") and number < len(lines):
            line = line.rstrip()[:-1].rstrip() + " " + lines[number].strip()
        results.append((number, *pin_problems(line, comments, previous)))
    return results


class InstallHintTests(unittest.TestCase):
    def test_each_install_sh_in_the_repository_comes_from_its_pinned_ref(self):
        names = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                               check=True, capture_output=True, text=True).stdout.split("\0")
        found = set()
        for name in filter(None, names):
            path = ROOT / name
            # The test files hold probe lines that are wrong on purpose.
            if not path.is_file() or re.fullmatch(r"scripts/test_\w+\.py", name):
                continue
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            for number, problems, programs in line_problems(text.splitlines(), comments=not name.endswith(".md")):
                self.assertEqual(problems, [], f"{name}:{number}")
                found |= programs
        self.assertEqual(found, set(REFS))

    def test_the_pin_check_catches_each_unpinned_line(self):
        good = HINT.format(name="jlog", ref="v0.3.0", tag="v0.3.0")
        self.assertEqual(pin_problems(f"Run `{good}`, then put ~/.local/bin on PATH."), ([], {"jlog"}))
        jagt = HINT.format(name="jagt", ref=REFS["jagt"], tag="v0.6.4")
        self.assertEqual(pin_problems(f"Run `{jagt}`. To build it, run `cargo install --tag v0.6.4 jagt`."),
                         ([], {"jagt"}))
        for bad in (good.replace("/v0.3.0/", "/main/"),
                    good.replace("/v0.3.0/", "/refs/heads/main/"),
                    # The name comes in by format, so the pin check of test_ci_check.py does not read this probe as a hint.
                    "curl -fsSL https://github.com/rahuldave/{}/raw/main/scripts/install.sh | sh -s -- --tag v0.3.0".format("jlog"),
                    good.replace("rahuldave", "RahulDave"),
                    good + "-rc1",
                    good + " --tag v0.2.0",
                    good.replace("--tag v0.3.0", "--tag v0.2.0"),
                    jagt.replace(REFS["jagt"], "7ea80a99492fe5eed5d7fa9b9a4e1ba08599463a"),
                    jagt.replace("--tag v0.6.4", "--tag v0.6.3"),
                    jagt.replace(REFS["jagt"], "main"),
                    good + ".1",
                    f"{good} or {good.replace('/v0.3.0/', '/main/')}",
                    f"| `jlog` | `{good}` |",
                    "Run its scripts/install.sh with --tag v0.3.0, as the README of jlog shows."):
            with self.subTest(line=bad):
                self.assertNotEqual(pin_problems(bad)[0], [])
        # A URL that a line break splits is checked as one line.
        unpinned = good.replace("/v0.3.0/", "/main/")
        cut = unpinned.index("install.sh")
        self.assertNotEqual(line_problems([unpinned[:cut], unpinned[cut:]])[1][1], [])
        cut = good.index("install.sh")
        self.assertEqual(line_problems([good[:cut], good[cut:]])[1][1], [])
        # A heading of Markdown is not a comment, and wrapped prose names the program on the line before.
        self.assertNotEqual(line_problems(["## Install jlog with its scripts/install.sh from main"], comments=False)[0][1], [])
        self.assertNotEqual(line_problems(["The release binary of jlog:", "run its scripts/install.sh from main."])[1][1], [])
        # A command that a backslash splits, and a hint that ends in HTML or before another command, pass.
        self.assertEqual(line_problems([good.split(" | sh")[0] + " \\", "  | sh" + good.split(" | sh")[1]])[0][1], [])
        for tail in ("</code>", "; echo ok", " && jlog --version"):
            self.assertEqual(pin_problems(f"<code>{good}{tail}"), ([], {"jlog"}), tail)
        # A comment of a workflow may say where install.sh comes from.
        self.assertEqual(pin_problems("        # install.sh of jlog comes from the tag."), ([], set()))


if __name__ == "__main__":
    unittest.main()
