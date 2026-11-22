#!/usr/bin/env python3
"""Make the next release tag vX.Y.Z on HEAD, by semantic versioning, push it, and check it on the remote.

Run it as `just release`, on a clean checkout of the integration branch, after the post-merge CI passed. It uses the
standard library only, and Python 3.9 or later.

The last tag is the newest tag vX.Y.Z that is an ancestor of HEAD. The script reads the conventional commit messages
since that tag, and skips the merge commits:

- A `!` after the type, as in `feat!: ...`, or a line `BREAKING CHANGE:` in the body, raises MAJOR. Below 1.0.0 it
  raises MINOR.
- `feat` raises MINOR. `fix`, `perf` and `refactor` raise PATCH.
- `docs`, `test`, `ci`, `chore` and `style` give no release.
- Any other type, and a message that is not a conventional commit, raises PATCH.
- A conventional subject in a bullet line of the body, such as `* feat!: drop the flag`, counts too. A squash commit
  of GitHub lists the commits of its PR that way. The bullet counts only when its type is feat, fix, perf, refactor,
  docs, test, chore, ci, build, style or revert, in lower case. A labelled bullet such as `- Removed: the old copies`
  is not a commit, and asks for no bump.

With no tag yet, the next tag is v0.1.0.

A language profile can give the version of its manifest. The script runs `just <profile>::version` for each name in
the key `profiles` of `.agents/stack.json`. The recipe prints X.Y.Z, or nothing when the manifest has no version, and
exits 2 when it cannot read the manifest. A profile without the recipe gives no version. The script fails when two
profiles give different versions, and when the version is lower than the last tag. With no tag yet, the tag is the
version.

A branch does not raise the version. Branches start from the same tag, so two branches that each raised it would
raise it to the same number, and the second merge would need a new commit and a new gate. The release raises it:

- When the version is at least the bump that the commits ask for, as after a raise by hand, the tag is v<version>,
  on HEAD, and the script makes it only when that tag does not exist yet.
- When the version is lower, the script writes the bump into the version file of each profile, and into its lock
  file, makes the commit `chore(release): vX.Y.Z` on the branch of HEAD, and tags that commit. It pushes the commit
  and the tag together, with `git push --atomic`. This commit asks for no bump, so the next run finds the tag and
  stops. The profiles that it can write are python (pyproject.toml and uv.lock), rust (Cargo.toml and Cargo.lock) and
  typescript (package.json and package-lock.json). It reads the TOML files with tomllib, so it needs Python 3.11 or
  later for them. It checks each file after the change: only the version is different, and each profile gives the
  new version. A failure after the write takes back the commit, the tag and the files.
- When the branch on the remote is not at HEAD, a later push came, and its run makes the release, so this run prints
  "no release".

`--check` is the step release-check of `just check`. It reads no remote and needs no network. It fails on the errors
of the version only: profiles that disagree, and a version lower than the last tag. A version equal to the last tag
passes, also when the commits ask for a bump, since the release writes the bump. When the release must write the
version, the check and the dry run make the changes in memory, so a file that the release cannot change fails here:
a profile with no writer, a file in another form, a manifest that git does not track, or a Cargo.toml that asks for a
version of a crate of the workspace. A lock file that git does not track is left as it is. In a shallow checkout, a
checkout with no release tag, or a repository with no commit, it says so and passes.

`just check` runs before the commit, so the message of the commit is not known yet. So the commit-msg hook of the
commit gate runs `just release-check` once more, with the path of the message file in the variable
`JN_RELEASE_MESSAGE`. The check then counts that message as one more commit after HEAD, for the next tag that it
prints, and for the profiles that the release must write. It counts the message cleaned up as git does:

- After an editor, git cuts the message at the scissors line for `git commit -v`, whose diff follows that line,
  and for the mode scissors. Else the lines after the scissors line stay.
- The cleanup mode is the one of `JN_RELEASE_CLEANUP`, which the gate takes from the option `--cleanup` of git,
  else the one of `commit.cleanup`, else default. The modes strip, and default after an editor, remove the comment
  lines. The modes whitespace, verbatim and scissors, and default without an editor, as for
  `git commit -m "#12 fix login"`, keep them, so they count.
- In a hook, git sets `GIT_EDITOR` to `:` when it runs no editor. Any other value, or none, means an editor. A person
  can set `GIT_EDITOR=:` too, so `JN_RELEASE_EDITOR=1`, which the gate sets when the command shows an editor, also
  means an editor. With `JN_RELEASE_EDITOR=unknown`, both may apply.
- `JN_RELEASE_CLEANUP=unknown` says that the gate cannot read the option. Then each mode may apply.
- The comment character is the one of `core.commentString` or `core.commentChar`, `#` by default. With `auto`, git
  picks one for each commit, so each one that git may pick may apply.

When more than one reading may apply, the reading that asks for the biggest bump counts.

A merge gives no commit to count, since the release skips merge commits: git merge writes `MERGE_HEAD`. For an
amend, the gate sets `JN_RELEASE_AMEND=1`, and the new message replaces the message of HEAD. An amend of a merge is
a merge. An amend of a commit with a release tag stops, since the tag stays on the old commit. With
`JN_RELEASE_AMEND=maybe`, the gate cannot tell an amend from a word `--amend` of the message. HEAD then counts, and
a release tag on HEAD stops the commit too.

`--dry-run` prints the next tag and the reason, and changes nothing. Without it, the script makes an annotated tag on
HEAD, or on the release commit, pushes it, and checks with `git ls-remote` that the remote tag points at that commit.
When the variable `GITHUB_OUTPUT` names a file, as in GitHub Actions, the script adds the lines `tag=vX.Y.Z` and
`commit=<hash>` to it, so that a later job can check out the tag. It never moves or deletes a tag.
When there is nothing to tag, it prints "no release" and exits 0. A tag at or above the next number on a later
commit also gives no release: a later commit was released first. A failure exits 1, also for a shallow checkout
and for a remote tag that this checkout lacks or has on another commit.

A run on a commit that is released already prints "already released", writes its tag and commit to GITHUB_OUTPUT,
and makes nothing. So "Re-run all jobs" of a release workflow, which runs the release again on the pushed commit,
gives the later jobs the tag again. The commit is released in two cases:

- HEAD has a release tag, as after a raise of the version by hand.
- A version commit with a release tag has HEAD as its only parent. The run trusts it only when its author is
  github-actions[bot], its subject is `chore(release): <tag>`, and its files are exactly the files that the release
  writes from HEAD for the tag. A commit that fails one of these rules is not the release of HEAD.

The tag must be on the remote too. The run reads the tags of the checkout, and fetches nothing. A dry run writes no
output. A run on the version commit itself, as a push with a token that starts workflows makes, gives no tag, since
the run of its parent gives it. That run checks the parent, the author, the subject and the names of the files.
"""

from __future__ import annotations

import argparse
import copy
import glob
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

Version = Tuple[int, int, int]

TAG = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
PLAIN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
SUBJECT = re.compile(r"^(?P<type>[A-Za-z]+)(\([^()]*\))?(?P<bang>!)?: \S")
BREAKING = re.compile(r"^[ \t]*(?:[*-][ \t]+)?BREAKING[ -]CHANGE:", re.MULTILINE)
# A line of the body such as "* feat!: drop the flag", as GitHub lists the commits of a PR in a squash commit. Only a
# known type in lower case counts, so a labelled bullet such as "- Removed: the old copies" asks for no bump.
BULLET_TYPES = ("feat", "fix", "perf", "refactor", "docs", "test", "chore", "ci", "build", "style", "revert")
BULLET = re.compile(r"^[ \t]*[*-][ \t]+(?P<subject>(?:%s)(?:\([^()\n]*\))?!?: \S.*)$" % "|".join(BULLET_TYPES),
                    re.MULTILINE)
NO_RELEASE = {"docs", "test", "ci", "chore", "style"}
PATCH_TYPES = {"fix", "perf", "refactor"}
LEVELS = ("none", "patch", "minor", "major")
FIRST: Version = (0, 1, 0)
STACK = ".agents/stack.json"
MESSAGE_VARIABLE = "JN_RELEASE_MESSAGE"
AMEND_VARIABLE = "JN_RELEASE_AMEND"
CLEANUP_VARIABLE = "JN_RELEASE_CLEANUP"
CLEANUP_MODES = ("default", "strip", "whitespace", "verbatim", "scissors")
EDITOR_VARIABLE = "JN_RELEASE_EDITOR"
# The characters that git picks from for core.commentChar=auto.
AUTO_COMMENT_CHARS = "#;@!$%^&|:"


class ReleaseError(Exception):
    """A reason to stop with exit 1."""


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def tag_name(version: Version) -> str:
    return "v%d.%d.%d" % version


def parse_tag(name: str) -> Optional[Version]:
    match = TAG.match(name)
    return None if match is None else (int(match[1]), int(match[2]), int(match[3]))


def last_tag(root: Path) -> Optional[Version]:
    """The newest tag vX.Y.Z that is an ancestor of HEAD, or None."""
    versions = [parse_tag(name) for name in git(root, "tag", "--merged", "HEAD", "--list", "v*").split()]
    found = [version for version in versions if version is not None]
    return max(found) if found else None


def subject_level(subject: str) -> Optional[str]:
    """The bump of a conventional subject, or None when the subject is not a conventional commit."""
    match = SUBJECT.match(subject.strip())
    if match is None:
        return None
    if match["bang"]:
        return "major"
    kind = match["type"].lower()
    if kind == "feat":
        return "minor"
    if kind in NO_RELEASE:
        return "none"
    return "patch"


def commit_level(message: str) -> str:
    """The bump that one commit message asks for: none, patch, minor or major. A conventional subject in a bullet
    line of the body counts too, since a squash commit lists the commits of its PR that way."""
    if BREAKING.search(message):
        return "major"
    subject, _, body = message.partition("\n")
    levels = [subject_level(subject) or "patch"]
    levels += [level for level in (subject_level(m["subject"]) for m in BULLET.finditer(body)) if level]
    return max(levels, key=LEVELS.index)


def commits_since(root: Path, since: Version) -> List[Tuple[str, str]]:
    """The hash and the message of each commit since the tag, without the merge commits."""
    text = git(root, "log", "--no-merges", "--format=%H%x1f%B%x1e", f"{tag_name(since)}..HEAD")
    commits = []
    for entry in text.split("\x1e"):
        entry = entry.strip("\n")
        if entry:
            sha, _, message = entry.partition("\x1f")
            commits.append((sha, message))
    return commits


def bump(version: Version, level: str) -> Version:
    major, minor, patch = version
    if level == "major" and major == 0:
        level = "minor"
    if level == "major":
        return (major + 1, 0, 0)
    if level == "minor":
        return (major, minor + 1, 0)
    if level == "patch":
        return (major, minor, patch + 1)
    return version


def profile_names(root: Path) -> List[str]:
    path = root / STACK
    if not path.is_file():
        return []
    try:
        stack = json.loads(path.read_text())
    except ValueError as error:
        raise ReleaseError(f"{STACK} is not JSON: {error}") from error
    names = stack.get("profiles") if isinstance(stack, dict) else None
    if not isinstance(names, list):
        return []
    # The same names as commit_gate.py takes: a name with a / or . or .. names no folder of .agents/just/.
    return [name for name in names if isinstance(name, str) and name not in ("", ".", "..")
            and all(c.isalnum() or c in "-_." for c in name)]


def profile_versions(root: Path) -> List[Tuple[str, Version]]:
    """The version that each profile gives, from its recipe <profile>::version."""
    names = profile_names(root)
    if not names:
        return []
    summary = subprocess.run(["just", "--summary"], cwd=root, capture_output=True, text=True)
    if summary.returncode != 0:
        raise ReleaseError(f"just --summary failed: {summary.stderr.strip()}")
    recipes = set(summary.stdout.split())
    versions = []
    for name in names:
        recipe = f"{name}::version"
        if recipe not in recipes:
            continue
        result = subprocess.run(["just", recipe], cwd=root, capture_output=True, text=True)
        if result.returncode == 2:
            raise ReleaseError(f"just {recipe} cannot read the manifest: {result.stderr.strip()}")
        if result.returncode != 0:
            raise ReleaseError(f"just {recipe} failed with exit {result.returncode}: {result.stderr.strip()}")
        text = result.stdout.strip()
        if not text:
            continue
        match = PLAIN.match(text)
        if match is None:
            raise ReleaseError(f"just {recipe} printed {text!r}, which is not a version X.Y.Z")
        versions.append((name, (int(match[1]), int(match[2]), int(match[3]))))
    return versions


def manifest_version(root: Path) -> Optional[Tuple[str, Version]]:
    versions = profile_versions(root)
    if not versions:
        return None
    if len({version for _, version in versions}) > 1:
        given = ", ".join(f"{name} gives {'%d.%d.%d' % version}" for name, version in versions)
        raise ReleaseError(f"the profiles give different versions: {given}. Make the manifests agree")
    return versions[0]


def tag_commit(root: Path, name: str) -> Optional[str]:
    """The commit of a local tag, or None when the tag does not exist."""
    result = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{name}^{{commit}}"], cwd=root,
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def check_remote_tags(root: Path, remote: str) -> Optional[Dict[str, str]]:
    """Fail when the remote has a release tag that the checkout lacks, since the next number would then be wrong. The
    commit of each release tag on the remote, or None when there is no such remote."""
    if remote not in git(root, "remote").split():
        return None
    result = subprocess.run(["git", "ls-remote", "--tags", remote], cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        raise ReleaseError(f"git ls-remote --tags {remote} failed: {result.stderr.strip()}")
    remote_commits = {}
    for line in result.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        name = ref[len("refs/tags/"):]
        peeled = name.endswith("^{}")
        name = name[:-3] if peeled else name
        if parse_tag(name) is not None and (peeled or name not in remote_commits):
            remote_commits[name] = sha
    missing = sorted(name for name in remote_commits if tag_commit(root, name) is None)
    if missing:
        raise ReleaseError(f"{remote} has the tags {', '.join(missing)}, which this checkout lacks. Run "
                           f"git fetch --tags {remote}, then run the release again")
    differ = sorted(name for name, sha in remote_commits.items() if tag_commit(root, name) != sha)
    if differ:
        raise ReleaseError(f"the tags {', '.join(differ)} point at other commits on {remote} than here. A pushed tag "
                           "never moves, so delete the local tags and fetch them again")
    return remote_commits


def is_ancestor(root: Path, older: str, newer: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", older, newer], cwd=root,
                          capture_output=True).returncode == 0


def newer_release(root: Path, version: Version, head: str) -> Optional[str]:
    """A tag at or above VERSION on a commit after HEAD, or None. Such a tag means a later commit was released first,
    for example when the CI of an older push finishes last, so this commit needs no tag of its own."""
    for name in git(root, "tag", "--list", "v*").split():
        found = parse_tag(name)
        if found is not None and found >= version:
            commit = tag_commit(root, name)
            if commit and commit != head and is_ancestor(root, head, commit):
                return name
    return None


# The author of the version commit in the CI starter. A re-run trusts a version commit only from this author.
RELEASE_BOT_NAME = "github-actions[bot]"
RELEASE_BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"
VERSION_FILES = ("pyproject.toml", "uv.lock", "Cargo.toml", "Cargo.lock", "package.json", "package-lock.json")


def parents(root: Path, commit: str) -> List[str]:
    return git(root, "rev-list", "--parents", "-n", "1", commit).split()[1:]


def distrust(root: Path, head: str, commit: str, name: str, full: bool = True) -> Optional[str]:
    """Why COMMIT, the child of HEAD with the tag NAME, is not a version commit of the release, or None when it is
    one: its only parent is HEAD, its author is the release bot, its subject is chore(release): NAME, and it changes
    only the version lines: the files of COMMIT are the ones that the release writes from HEAD for NAME. Without FULL,
    it checks the parent, the author, the subject and the names of the files only, and needs no checkout of HEAD."""
    if parents(root, commit) != [head]:
        return f"{commit[:12]} has other parents than HEAD"
    author, email, subject = git(root, "log", "-1", "--format=%an%x1f%ae%x1f%s", commit).rstrip("\n").split("\x1f")
    if (author, email) != (RELEASE_BOT_NAME, RELEASE_BOT_EMAIL):
        return f"the author of {commit[:12]} is {author} <{email}>, not {RELEASE_BOT_NAME}"
    if subject != f"chore(release): {name}":
        return f"the subject of {commit[:12]} is not chore(release): {name}"
    raw = git(root, "diff", "--raw", "--no-renames", "--no-ext-diff", head, commit).splitlines()
    if not raw:
        return f"{commit[:12]} changes no file"
    for line in raw:
        fields, _, path = line.partition("\t")
        old_mode, new_mode, _, _, status = fields.lstrip(":").split()
        if status != "M" or old_mode != new_mode or old_mode != "100644" or path not in VERSION_FILES:
            return f"{commit[:12]} changes {path}, which is not a version file that the release writes"
    if not full:
        return None
    changed = sorted(line.partition("\t")[2] for line in raw)
    if git(root, "status", "--porcelain", "--untracked-files=no").strip():
        return "the checkout has changes, so the files that the release writes from HEAD are unknown"
    # The version commit must hold exactly what the release writes from HEAD. Git stores the planned text in the
    # form of the commit, after the conversions of .gitattributes, such as eol=crlf.
    try:
        manifest = manifest_version(root)
        version = parse_tag(name)
        if manifest is None or version is None:
            return "the profiles of HEAD give no version"
        changes = planned_changes(root, manifest[1], version)
        planned = {str(path.relative_to(root)): text for path, text in changes.items()}
    except ReleaseError as error:
        return f"the release cannot write {name} from HEAD: {error}"
    if changed != sorted(planned):
        return f"{commit[:12]} changes {', '.join(changed)}, but the release writes {', '.join(sorted(planned))}"
    for path, text in planned.items():
        stored = subprocess.run(["git", "hash-object", f"--path={path}", "--stdin"], cwd=root,
                                input=text.encode("utf-8"), capture_output=True)
        blob = git(root, "rev-parse", f"{commit}:{path}").strip()
        if stored.returncode != 0 or stored.stdout.decode().strip() != blob:
            return f"{commit[:12]} changes more than the version lines of {path}"
    return None


def released_child(root: Path, head: str) -> Tuple[Optional[Tuple[str, str]], List[str]]:
    """The tag and the commit of a version commit of the release whose parent is HEAD, as a re-run on the pushed
    commit finds it, or None. Also the reason for each child of HEAD with a release tag that is not trusted."""
    found: List[Tuple[Version, str, str]] = []
    reasons = []
    for name in git(root, "tag", "--list", "v*").split():
        version = parse_tag(name)
        commit = tag_commit(root, name) if version is not None else None
        if version is None or commit is None or commit == head or head not in parents(root, commit):
            continue
        reason = distrust(root, head, commit, name)
        if reason is None:
            found.append((version, name, commit))
        else:
            reasons.append(f"{name}: {reason}")
    if not found:
        return None, reasons
    _, name, commit = max(found)
    return (name, commit), reasons


def config_value(root: Path, key: str) -> str:
    result = subprocess.run(["git", "config", "--get", key], cwd=root, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def comment_chars(root: Path) -> List[str]:
    """The comment strings that git may use, from core.commentString or core.commentChar, `#` by default. With `auto`,
    git picks a character for each commit that the check cannot know, so each one that git may pick counts."""
    for key in ("core.commentString", "core.commentChar"):
        value = config_value(root, key)
        if value:
            return [value] if value != "auto" else list(AUTO_COMMENT_CHARS)
    return ["#"]


def cleanup_modes(root: Path) -> List[str]:
    """The cleanup modes that git may use for the commit: the one of JN_RELEASE_CLEANUP, which the gate takes from
    the option --cleanup of git, else the one of commit.cleanup, else default. With `unknown`, or a value that is not
    a mode, each mode may apply."""
    given = os.environ.get(CLEANUP_VARIABLE, "").strip()
    if not given:
        given = config_value(root, "commit.cleanup") or "default"
    return [given] if given in CLEANUP_MODES else list(CLEANUP_MODES)


def strips_comments(mode: str, editor: bool) -> bool:
    """True when git removes the comment lines of the message. The mode scissors keeps the comment lines above the
    scissors line, and without an editor the modes default and scissors are whitespace."""
    return mode == "strip" or (mode == "default" and editor)


def pending_message(root: Path) -> Optional[str]:
    """The message of the commit being made, from the file that JN_RELEASE_MESSAGE names, as git cleans it up. None
    when the variable is not set, or the message is empty, so git makes no commit. When git may clean it up in more
    than one way, the reading that asks for the biggest bump counts."""
    path = os.environ.get(MESSAGE_VARIABLE)
    if not path:
        return None
    try:
        text = Path(path).read_text(errors="replace")
    except OSError as error:
        raise ReleaseError(f"{MESSAGE_VARIABLE} names {path}, which cannot be read: {error}") from error
    lines = text.splitlines()
    # Any short prefix, since with core.commentChar=auto git may pick another character.
    scissors = re.compile(r"^\S{1,8} -+ >8 -+$")
    cut = next((index for index, line in enumerate(lines) if scissors.match(line)), None)
    chars = comment_chars(root)
    # git commit -v puts the diff after the scissors line and its comment lines.
    after = [line for line in lines[cut + 1:] if not line.startswith(tuple(chars))] if cut is not None else []
    verbose = bool(after) and after[0].startswith("diff --git ")
    # In a hook, git sets GIT_EDITOR to ":" when it runs no editor, as for git commit -m. A person can set it too, so
    # the gate sets JN_RELEASE_EDITOR=1 when the command shows that git runs the editor, and unknown when an option
    # after the text of the message can hide it.
    given = os.environ.get(EDITOR_VARIABLE)
    if os.environ.get("GIT_EDITOR") != ":" or given == "1":
        editors = [True]
    else:
        editors = [False, True] if given == "unknown" else [False]
    readings = []
    for editor in editors:
        for mode in cleanup_modes(root):
            # Git cuts at the scissors line for -v and for the mode scissors, both only after an editor. Else the
            # line is text, or a comment line, and the lines after it stay.
            part = lines[:cut] if cut is not None and editor and (verbose or mode == "scissors") else lines
            strip = strips_comments(mode, editor)
            for char in chars if strip else [""]:
                kept = [line for line in part if not (strip and line.startswith(char))]
                reading = "\n".join(kept).strip()
                if reading and reading not in readings:
                    readings.append(reading)
    return max(readings, key=lambda message: LEVELS.index(commit_level(message)), default=None)


def tag_on_head(root: Path) -> Optional[str]:
    """A release tag on HEAD, or None."""
    names = [name for name in git(root, "tag", "--points-at", "HEAD", "--list", "v*").split() if parse_tag(name)]
    return max(names, key=parse_tag) if names else None


def is_merge(root: Path, amend: bool) -> bool:
    """True when the commit being made is a merge: git merge writes MERGE_HEAD, and an amend of a merge is a merge."""
    if subprocess.run(["git", "rev-parse", "--verify", "--quiet", "MERGE_HEAD"], cwd=root,
                      capture_output=True).returncode == 0:
        return True
    return amend and len(git(root, "rev-list", "--parents", "-n", "1", "HEAD").split()) > 2


class Plan(NamedTuple):
    """The next tag, or None for no release, the reason, and the version that the release must write into the
    profiles first, or None when the profiles already give the version of the tag."""
    version: Optional[Version]
    reason: str
    write: Optional[Version] = None


def show(version: Version) -> str:
    return "%d.%d.%d" % version


def plan(root: Path, pending: Optional[str] = None, amend: bool = False) -> Plan:
    """The next tag and the reason. PENDING is the message of the commit being made, which counts as one more commit
    after HEAD. With AMEND, it replaces the message of HEAD."""
    last = last_tag(root)
    manifest = manifest_version(root)
    if last is None:
        if manifest is not None:
            return Plan(manifest[1], f"no tag yet, and the profile {manifest[0]} gives the version")
        return Plan(FIRST, "no tag yet")
    commits = commits_since(root, last)
    if pending is not None and amend:
        # An amend replaces HEAD, so its new message counts and the old one does not.
        head = git(root, "rev-parse", "HEAD").strip()
        commits = [(sha, message) for sha, message in commits if sha != head]
    messages = [message for _, message in commits]
    count = f"{len(messages)} commit(s) since {tag_name(last)}"
    if pending is not None:
        messages.append(pending)
        count += " and the commit being made"
    level = max((commit_level(message) for message in messages), key=LEVELS.index, default="none")
    asked = bump(last, level)
    since = f"{count} ask for {level}"
    if manifest is None:
        if level == "none":
            return Plan(None, since)
        return Plan(asked, since)
    profile, version = manifest
    if version < last:
        raise ReleaseError(f"the profile {profile} gives {show(version)}, which is lower than the last tag "
                           f"{tag_name(last)}")
    if version < asked:
        return Plan(asked, f"{since}, and the profile {profile} gives {show(version)}, so the release writes "
                           f"{show(asked)} into the version files", asked)
    if version == last:
        return Plan(None, f"{since}, and the profile {profile} gives {show(version)}, which is tagged")
    return Plan(version, f"{since}, and the profile {profile} gives {show(version)}")


# Writing the version. Each writer changes the version line of the manifest and of its lock file as text, so the
# rest of each file stays as it is, and then checks that the file, read again, differs only in the version.

def load_toml(path: Path, text: str) -> Dict[str, Any]:
    try:
        import tomllib
    except ImportError as error:
        raise ReleaseError(f"writing the version into {path.name} needs tomllib, of Python 3.11 or later") from error
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ReleaseError(f"{path} is not TOML: {error}") from error


def read_raw(path: Path) -> str:
    """The text of PATH with its line endings as they are, so that a file with CRLF keeps them."""
    try:
        with open(path, newline="", encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError) as error:
        raise ReleaseError(f"cannot read {path}: {error}") from error


def write_raw(path: Path, text: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        handle.write(text)


HEADER = re.compile(r"^[ \t]*\[(?P<name>[^\[\]]+)\][ \t]*(?:#.*)?$")
ARRAY_HEADER = re.compile(r"^[ \t]*\[\[(?P<name>[^\[\]]+)\]\][ \t]*(?:#.*)?$")


def table_name(text: str) -> Tuple[str, ...]:
    return tuple(part.strip().strip("\"'") for part in text.split("."))


def version_line(old: str) -> "re.Pattern[str]":
    return re.compile(r"^(?P<lead>[ \t]*version[ \t]*=[ \t]*)(?P<q>[\"'])%s(?P=q)(?P<tail>[ \t]*(?:#.*)?)$"
                      % re.escape(old))


def replace_version(lines: List[str], index: int, old: str, new: str) -> None:
    match = version_line(old).match(lines[index].rstrip("\r\n"))
    assert match is not None
    ending = lines[index][len(lines[index].rstrip("\r\n")):]
    lines[index] = f"{match['lead']}{match['q']}{new}{match['q']}{match['tail']}{ending}"


def set_table_version(path: Path, table: Tuple[str, ...], old: str, new: str) -> str:
    """The text of the TOML file PATH with the key version of TABLE changed from OLD to NEW. It fails unless the key is
    one line `version = "OLD"` in the header of the table, and unless the file, read again, differs in that key only."""
    text = read_raw(path)
    data = load_toml(path, text)
    lines = text.splitlines(keepends=True)
    current: Optional[Tuple[str, ...]] = ()
    pattern = version_line(old)
    found = []
    for index, line in enumerate(lines):
        bare = line.rstrip("\r\n")
        header = HEADER.match(bare)
        if header is not None:
            current = table_name(header["name"])
        elif ARRAY_HEADER.match(bare):
            current = None
        elif current == table and pattern.match(bare):
            found.append(index)
    where = "[" + ".".join(table) + "]"
    if len(found) != 1:
        raise ReleaseError(f"{path.name} has no line version = \"{old}\" in {where} that the release can change. "
                           "Raise the version by hand in a pull request")
    replace_version(lines, found[0], old, new)
    result = "".join(lines)
    expected = copy.deepcopy(data)
    node = expected
    for key in table:
        node = node[key]
    node["version"] = new
    if load_toml(path, result) != expected:
        raise ReleaseError(f"changing the version line of {path.name} changed more than {where} version. Raise the "
                           "version by hand in a pull request")
    return result


def set_lock_versions(path: Path, chosen: List[int], old: str, new: str) -> str:
    """The text of the lock file PATH, with the version of each [[package]] whose index is in CHOSEN changed from OLD
    to NEW, as Cargo.lock and uv.lock keep it. It checks that only those versions changed."""
    text = read_raw(path)
    data = load_toml(path, text)
    packages = data.get("package")
    if not isinstance(packages, list):
        raise ReleaseError(f"{path.name} has no [[package]] list")
    lines = text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if ARRAY_HEADER.match(line.rstrip("\r\n"))
              and table_name(ARRAY_HEADER.match(line.rstrip("\r\n"))["name"]) == ("package",)]
    if len(starts) != len(packages):
        raise ReleaseError(f"{path.name} has {len(starts)} lines [[package]] for {len(packages)} packages. Raise the "
                           "version by hand in a pull request")
    pattern = version_line(old)
    for number in chosen:
        index = starts[number] + 1
        while index < len(lines):
            bare = lines[index].rstrip("\r\n")
            if HEADER.match(bare) or ARRAY_HEADER.match(bare):
                index = len(lines)
                break
            if pattern.match(bare):
                break
            index += 1
        if index >= len(lines):
            raise ReleaseError(f"{path.name} has no line version = \"{old}\" for the package "
                               f"{packages[number].get('name')}. Raise the version by hand in a pull request")
        replace_version(lines, index, old, new)
    result = "".join(lines)
    expected = copy.deepcopy(data)
    for number in chosen:
        expected["package"][number]["version"] = new
    if load_toml(path, result) != expected:
        raise ReleaseError(f"changing the versions of {path.name} changed more than the versions. Raise the version "
                           "by hand in a pull request")
    return result


def normal_name(name: str) -> str:
    """The name of a Python package in the normal form that uv.lock uses."""
    return re.sub(r"[-_.]+", "-", name).lower()


def write_python(root: Path, old: str, new: str) -> Dict[Path, str]:
    """pyproject.toml [project] version, and the package of the project in uv.lock."""
    manifest = root / "pyproject.toml"
    changes = {manifest: set_table_version(manifest, ("project",), old, new)}
    lock = root / "uv.lock"
    if lock.is_file():
        name = normal_name(str(load_toml(manifest, manifest.read_text())["project"].get("name", "")))
        packages = load_toml(lock, lock.read_text()).get("package") or []
        chosen = [number for number, package in enumerate(packages)
                  if isinstance(package, dict) and normal_name(str(package.get("name", ""))) == name
                  and package.get("version") == old
                  and package.get("source") in ({"editable": "."}, {"virtual": "."})]
        if chosen:
            changes[lock] = set_lock_versions(lock, chosen, old, new)
    return changes


def versioned_dependencies(data: Dict[str, Any], names: Any) -> List[str]:
    """The crates of NAMES that a dependency table of the manifest DATA asks for with a version."""
    tables = [data.get(key) for key in ("dependencies", "dev-dependencies", "build-dependencies")]
    workspace = data.get("workspace")
    if isinstance(workspace, dict):
        tables.append(workspace.get("dependencies"))
    target = data.get("target")
    if isinstance(target, dict):
        for spec in target.values():
            if isinstance(spec, dict):
                tables += [spec.get(key) for key in ("dependencies", "dev-dependencies", "build-dependencies")]
    found = []
    for table in tables:
        if not isinstance(table, dict):
            continue
        for key, value in table.items():
            crate = value.get("package", key) if isinstance(value, dict) else key
            if crate in names and isinstance(value, dict) and "version" in value:
                found.append(crate)
    return found


def member_manifests(root: Path, workspace: Dict[str, Any]) -> List[Path]:
    """The Cargo.toml of each member of the workspace, other than the root package."""
    members = workspace.get("members") or []
    excluded = {(root / name).resolve() for name in workspace.get("exclude") or [] if isinstance(name, str)}
    found = []
    seen = set()
    for pattern in members:
        if not isinstance(pattern, str):
            continue
        for folder in sorted(glob.glob(str(root / pattern))):
            folder_path = Path(folder).resolve()
            manifest = folder_path / "Cargo.toml"
            if (folder_path == root.resolve() or folder_path in excluded or folder_path in seen
                    or not manifest.is_file()):
                continue
            seen.add(folder_path)
            found.append(manifest)
    return found


def cargo_members(root: Path, workspace: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The [package] tables of the members of the workspace, other than the root package."""
    packages = [load_toml(path, path.read_text()).get("package") for path in member_manifests(root, workspace)]
    return [package for package in packages if isinstance(package, dict)]


def write_rust(root: Path, old: str, new: str) -> Dict[Path, str]:
    """Cargo.toml [package] version, or [workspace.package] version when the package inherits it or the root has no
    package, as the profile reads it. In Cargo.lock, the packages of the workspace that take that version, which have
    no source."""
    manifest = root / "Cargo.toml"
    data = load_toml(manifest, manifest.read_text())
    package = data.get("package") if isinstance(data.get("package"), dict) else None
    workspace = data.get("workspace") if isinstance(data.get("workspace"), dict) else {}
    names = set()
    if package is not None and isinstance(package.get("version"), str):
        table: Tuple[str, ...] = ("package",)
        names.add(package.get("name"))
    else:
        table = ("workspace", "package")
        inherits = [package] if package is not None else []
        inherits += cargo_members(root, workspace)
        names.update(member.get("name") for member in inherits if member.get("version") == {"workspace": True})
    manifests = [data] + [load_toml(path, path.read_text()) for path in member_manifests(root, workspace)]
    pinned = sorted({name for found in manifests for name in versioned_dependencies(found, names)})
    if pinned:
        raise ReleaseError(f"a Cargo.toml asks for a version of the workspace crate {', '.join(pinned)}, and the "
                           "release does not change that requirement. Raise the version by hand in a pull request")
    changes = {manifest: set_table_version(manifest, table, old, new)}
    lock = root / "Cargo.lock"
    if lock.is_file():
        packages = load_toml(lock, lock.read_text()).get("package") or []
        counted = [entry.get("name") for entry in packages if isinstance(entry, dict)]
        twice = sorted({name for name in names if counted.count(name) > 1})
        if twice:
            raise ReleaseError(f"Cargo.lock has more than one package {', '.join(twice)}. Raise the version by hand "
                               "in a pull request")
        chosen = [number for number, entry in enumerate(packages)
                  if isinstance(entry, dict) and entry.get("name") in names and entry.get("version") == old
                  and "source" not in entry]
        if chosen:
            changes[lock] = set_lock_versions(lock, chosen, old, new)
    return changes


def set_json_version(path: Path, old: str, new: str, lock: bool) -> Optional[str]:
    """The text of the JSON file PATH with its key version, and for a lock file the version of packages[""], changed
    from OLD to NEW. The file must be in the form that npm writes, with an indent of 2 spaces, 4 spaces or a tab, so
    that writing it again changes only the version. None when the file holds no such version."""
    text = read_raw(path)
    try:
        data = json.loads(text)
    except ValueError as error:
        raise ReleaseError(f"{path} is not JSON: {error}") from error
    if not isinstance(data, dict):
        raise ReleaseError(f"{path} is not a JSON object")
    ending = "\n" if text.endswith("\n") else ""
    indent = next((step for step in (2, 4, "\t")
                   if json.dumps(data, indent=step, ensure_ascii=False) + ending == text), None)
    if indent is None:
        raise ReleaseError(f"{path.name} is not in the form that npm writes, so the release cannot change only its "
                           "version. Raise the version by hand in a pull request")
    changed = False
    if data.get("version") == old:
        data["version"] = new
        changed = True
    root_package = data.get("packages", {}).get("") if lock and isinstance(data.get("packages"), dict) else None
    if isinstance(root_package, dict) and root_package.get("version") == old:
        root_package["version"] = new
        changed = True
    if not changed:
        return None
    return json.dumps(data, indent=indent, ensure_ascii=False) + ending


def write_typescript(root: Path, old: str, new: str) -> Dict[Path, str]:
    """package.json version, and the version of the project in package-lock.json."""
    manifest = root / "package.json"
    text = set_json_version(manifest, old, new, lock=False)
    if text is None:
        raise ReleaseError(f"package.json has no version {old} that the release can change")
    changes = {manifest: text}
    lock = root / "package-lock.json"
    if lock.is_file():
        text = set_json_version(lock, old, new, lock=True)
        if text is not None:
            changes[lock] = text
    return changes


LOCK_FILES = ("uv.lock", "Cargo.lock", "package-lock.json")
WRITERS = {"python": write_python, "rust": write_rust, "typescript": write_typescript}


def unwritable(root: Path) -> List[str]:
    """The profiles that give a version, and whose version file the release cannot write."""
    return [name for name, _ in profile_versions(root) if name not in WRITERS]


def planned_changes(root: Path, old: Version, new: Version) -> Dict[Path, str]:
    """The new text of each version file and lock file, with NEW in place of OLD, without writing it. It fails when a
    profile has no writer, when a file is not in a form that the writer can change, and when a file is not tracked
    by git, since the version commit holds only the version lines of tracked files."""
    given = profile_versions(root)
    missing = [name for name, _ in given if name not in WRITERS]
    if missing:
        raise ReleaseError(f"the release cannot write the version of the profile {', '.join(missing)}. Raise the "
                           f"version to {show(new)} by hand in a pull request")
    changes: Dict[Path, str] = {}
    for name, version in given:
        if version != old:
            raise ReleaseError(f"the profile {name} gives {show(version)}, not {show(old)}")
        changes.update(WRITERS[name](root, show(old), show(new)))
    for path in list(changes):
        relative = str(path.relative_to(root))
        if git(root, "ls-files", "--", relative).strip():
            continue
        if path.name in LOCK_FILES:
            # A library can keep its lock file out of git. A fresh clone has none, so the release leaves it alone.
            del changes[path]
            continue
        raise ReleaseError(f"{relative} is not tracked by git, so the version commit cannot hold it. Commit it, "
                           "or raise the version by hand in a pull request")
    return changes


def can_write(root: Path, new: Version) -> None:
    """Fail when the release could not write NEW into the profiles, as the check and the dry run find before the
    release. Without tomllib, it checks only that each profile has a writer."""
    try:
        import tomllib  # noqa: F401
    except ImportError:
        missing = unwritable(root)
        if missing:
            raise ReleaseError(f"the release cannot write the version of the profile {', '.join(missing)}. Raise "
                               f"the version to {show(new)} by hand in a pull request")
        return
    manifest = manifest_version(root)
    assert manifest is not None
    planned_changes(root, manifest[1], new)


def write_versions(root: Path, old: Version, new: Version) -> List[Path]:
    """Write NEW into the version file of each profile that gives OLD, and into its lock file, and check that each
    profile then gives NEW. The files that changed, in order."""
    given = profile_versions(root)
    changes = planned_changes(root, old, new)
    for path, text in changes.items():
        write_raw(path, text)
    paths = sorted(changes)
    try:
        after = profile_versions(root)
        wrong = [f"{name} gives {show(version)}" for name, version in after if version != new]
        if wrong or len(after) != len(given):
            raise ReleaseError(f"after writing {show(new)}, the profiles give: {', '.join(wrong) or 'fewer versions'}")
    except ReleaseError:
        git(root, "checkout", "--", *[str(path.relative_to(root)) for path in paths])
        raise
    return paths


def write_output(values: Dict[str, str]) -> None:
    """Add KEY=VALUE lines to the file of GITHUB_OUTPUT, when it is set, for the later jobs of the workflow."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def current_branch(root: Path) -> str:
    result = subprocess.run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=root, capture_output=True,
                            text=True)
    if result.returncode != 0:
        raise ReleaseError("HEAD is detached, so the release has no branch for its version commit. Check out the "
                           "branch, as actions/checkout does on a push")
    return result.stdout.strip()


def remote_branch(root: Path, remote: str, branch: str) -> Optional[str]:
    result = subprocess.run(["git", "ls-remote", "--heads", remote, f"refs/heads/{branch}"], cwd=root,
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise ReleaseError(f"git ls-remote {remote} failed: {result.stderr.strip()}")
    words = result.stdout.split()
    return words[0] if words else None


def has_commit(root: Path, sha: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=root, capture_output=True).returncode == 0


def already_released(root: Path, remote: str, remote_tags: Optional[Dict[str, str]], head: str,
                     dry_run: bool) -> Optional[str]:
    """The message of a run on a commit that is released already, after it writes the tag and its commit to
    GITHUB_OUTPUT, or None. HEAD is released when it has a release tag, as after a raise of the version by hand, or
    when a trusted version commit of the release, whose parent is HEAD, has one. So "Re-run all jobs" of a release
    workflow gives the later jobs the tag again. The tag must be on the remote, when there is one. A run on the
    version commit itself, as a push with a token that starts workflows makes, gives no tag, since the run of its
    parent gives it. A dry run writes no output."""
    tagged = tag_on_head(root)
    if tagged is not None:
        above = parents(root, head)
        # The checkout is at the version commit, not at its parent, so the check of its files is left out. A
        # wrong answer here gives no tag, as before the re-run rule.
        if len(above) == 1 and distrust(root, above[0], head, tagged, full=False) is None:
            return f"no release: HEAD is the version commit of {tagged}, and the run of its parent gives the tag"
        name, commit, where = tagged, head, "HEAD"
    else:
        child, _ = released_child(root, head)
        if child is None:
            return None
        name, commit = child
        where = f"the version commit {commit[:12]}, whose parent is HEAD"
    if remote_tags is not None and remote_tags.get(name) != commit:
        raise ReleaseError(f"{name} is on {where} here, but not on {remote}. Push it with git push {remote} "
                           f"refs/tags/{name}, then run the release again")
    if not dry_run:
        write_output({"tag": name, "commit": commit})
    return f"already released: {name} is on {where}, so the run makes nothing"


def release(root: Path, remote: str, dry_run: bool) -> str:
    if git(root, "rev-parse", "--is-shallow-repository").strip() == "true":
        raise ReleaseError("the checkout is shallow, so the last tag and the commits since it are unknown. Fetch the "
                           "whole history, for example with fetch-depth: 0 in actions/checkout")
    remote_tags = check_remote_tags(root, remote)
    head = git(root, "rev-parse", "HEAD").strip()
    done = already_released(root, remote, remote_tags, head, dry_run)
    if done is not None:
        return done
    version, reason, write = plan(root)
    if version is None:
        return f"no release: {reason}"
    name = tag_name(version)
    newer = newer_release(root, version, head)
    if newer is not None:
        _, untrusted = released_child(root, head)
        note = "".join(f". Not trusted as the release of HEAD: {why}" for why in untrusted)
        return f"no release: {newer} is on a later commit, so a later release has this commit{note}"
    existing = tag_commit(root, name)
    if existing is not None:
        if existing == head:
            write_output({"tag": name, "commit": head})
            return f"no release: {name} is already on HEAD"
        raise ReleaseError(f"{name} already exists on {existing[:12]}, which is not HEAD. A pushed tag never moves")
    if not dry_run and git(root, "status", "--porcelain", "--untracked-files=no").strip():
        raise ReleaseError("the checkout has changes, and the profiles read the version from the files. Run the "
                           "release in a clean checkout")
    if write is not None:
        return release_commit(root, remote, dry_run, version, reason, head)
    if dry_run:
        return f"next tag: {name} ({reason})"
    git(root, "tag", "-a", name, "-m", name, head)
    git(root, "push", remote, f"refs/tags/{name}:refs/tags/{name}")
    pushed = git(root, "ls-remote", remote, f"refs/tags/{name}^{{}}").split()
    if not pushed or pushed[0] != head:
        raise ReleaseError(f"{remote} does not show {name} on {head[:12]} after the push")
    write_output({"tag": name, "commit": head})
    return f"tagged {name} on {head[:12]} and pushed it to {remote} ({reason})"


def release_commit(root: Path, remote: str, dry_run: bool, version: Version, reason: str, head: str) -> str:
    """Write VERSION into the profiles, commit it on the branch of HEAD, tag the commit, and push both at once."""
    name = tag_name(version)
    can_write(root, version)
    if dry_run:
        return f"next tag: {name} ({reason}, and commits it as chore(release): {name})"
    branch = current_branch(root)
    tip = remote_branch(root, remote, branch) if remote in git(root, "remote").split() else head
    if tip is None:
        raise ReleaseError(f"{remote} has no branch {branch}, so the release has nowhere to push its version commit")
    if tip != head:
        if has_commit(root, tip) and is_ancestor(root, tip, head):
            raise ReleaseError(f"HEAD has commits that {remote}/{branch} lacks. Push them first, through a pull "
                               "request")
        return (f"no release: {remote}/{branch} is at {tip[:12]}, not at HEAD {head[:12]}, so the run of the later "
                "push makes the release")
    last = last_tag(root)
    assert last is not None
    paths = write_versions(root, manifest_version(root)[1], version)
    relative = [str(path.relative_to(root)) for path in paths]
    message = (f"chore(release): {name}\n\nThe commits since {tag_name(last)} ask for the release {name}. This "
               "commit changes only the version lines.")
    try:
        git(root, "add", "--", *relative)
        git(root, "commit", "-q", "-m", message, "--", *relative)
        commit = git(root, "rev-parse", "HEAD").strip()
        git(root, "tag", "-a", name, "-m", name, commit)
        push = subprocess.run(["git", "push", "--atomic", remote, f"{commit}:refs/heads/{branch}",
                               f"refs/tags/{name}:refs/tags/{name}"], cwd=root, capture_output=True, text=True)
        if push.returncode != 0:
            raise ReleaseError(f"git push --atomic of the version commit and {name} to {remote} failed, so neither "
                               f"was pushed: {push.stderr.strip()}")
    except ReleaseError as error:
        try:
            moved: Optional[str] = remote_branch(root, remote, branch)
        except ReleaseError:
            moved = None
        made = tag_commit(root, name)
        if moved is None or made is None or moved != made:
            undo(root, head, name, relative)
            if moved is not None and moved != head:
                return (f"no release: {remote}/{branch} moved to {moved[:12]} during the release, so the run of the "
                        "later push makes the release")
            raise ReleaseError(f"{error}. The release took back its commit, its tag and its changes. A rule of "
                               f"{remote} that blocks a push to {branch} stops it: let the token of the release job "
                               "push there") from error
        # git push failed after the remote took both refs, as when the connection drops. The release is out.
        commit = made
    pushed = git(root, "ls-remote", remote, f"refs/tags/{name}^{{}}").split()
    if not pushed or pushed[0] != commit:
        raise ReleaseError(f"{remote} does not show {name} on {commit[:12]} after the push")
    write_output({"tag": name, "commit": commit})
    return (f"wrote {show(version)} into {', '.join(relative)}, committed it as {commit[:12]} on {branch}, tagged "
            f"{name} and pushed both to {remote} ({reason})")


def undo(root: Path, head: str, name: str, relative: List[str]) -> None:
    """Take back the version commit, its tag and the written files, so the checkout is at HEAD again and clean."""
    if tag_commit(root, name) is not None:
        git(root, "tag", "-d", name)
    if git(root, "rev-parse", "HEAD").strip() != head:
        git(root, "reset", "-q", "--keep", head)
    git(root, "checkout", "-q", head, "--", *relative)


def check(root: Path) -> str:
    """The step release-check: the plan without the network and without the remote. It fails on the errors of the
    version only, which a commit or a pull request can fix: profiles that disagree, a version lower than the last tag,
    and a bump that the release cannot write. A version equal to the last tag passes, since the release writes the
    bump. A shallow checkout has no last tag to compare with, so it passes."""
    if subprocess.run(["git", "rev-parse", "--verify", "--quiet", "HEAD"], cwd=root, capture_output=True).returncode:
        return "release-check: no commit yet, so there is nothing to check"
    if git(root, "rev-parse", "--is-shallow-repository").strip() == "true":
        return ("release-check: the checkout is shallow, so the tags and the commits since the last tag are unknown. "
                "Passed without a check. Fetch the whole history with its tags to check the version")
    manifest_version(root)  # profiles that disagree fail with or without a tag
    if not git(root, "tag", "--list", "v*").split():
        return ("release-check: no release tag in this checkout, so there is no version to compare with. Passed. "
                "If the remote has tags, fetch them with git fetch --tags to check the version")
    given = os.environ.get(AMEND_VARIABLE)
    amend = given == "1"
    pending = None
    if os.environ.get(MESSAGE_VARIABLE) and not is_merge(root, amend):
        pending = pending_message(root)
        tagged = tag_on_head(root) if given in ("1", "maybe") else None
        if tagged is not None and amend:
            raise ReleaseError(f"HEAD is the release {tagged}, and an amend makes a new commit without the tag. A "
                               "pushed tag never moves, so the release would fail. Make a new commit instead")
        if tagged is not None:
            raise ReleaseError(f"HEAD is the release {tagged}, and the git command has the word --amend after the "
                               "message, so it may be an amend, which makes a new commit without the tag. Make a new "
                               "commit instead. If the word is part of the message, give the message with -F, or "
                               "put --amend out of it")
    version, reason, write = plan(root, pending, amend)
    if version is None:
        return f"release-check: no release ({reason})"
    if write is not None:
        try:
            can_write(root, write)
        except ReleaseError as error:
            raise ReleaseError(f"{reason}, but {error}") from error
    return f"release-check: the next tag is {tag_name(version)} ({reason})"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Make the next release tag vX.Y.Z on HEAD, push it and check it.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print the next tag and the reason, and change nothing")
    mode.add_argument("--check", action="store_true",
                      help="the step release-check: check the version against the tags, offline, and change nothing")
    parser.add_argument("--remote", default="origin", help="the remote to push the tag to (default origin)")
    args = parser.parse_args(argv)
    try:
        root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
        print(check(root) if args.check else release(root, args.remote, args.dry_run))
    except ReleaseError as error:
        print(f"release: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"release: cannot run a program, such as git or just: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
