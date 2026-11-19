"""Tests of release_tag.py, in a scratch repository with a bare origin, and a stub profile recipe for the version."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Optional
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/gpa/scripts/release_tag.py"
sys.path.insert(0, str(SCRIPT.parent))
import release_tag  # noqa: E402


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


class CommitLevelTests(unittest.TestCase):
    def test_each_type_gives_its_bump(self) -> None:
        cases = {
            "feat: add a page": "minor",
            "feat(api): add a call": "minor",
            "fix: stop a crash": "patch",
            "perf: cache the list": "patch",
            "refactor: split a module": "patch",
            "build: pin uv": "patch",
            "docs: fix a typo": "none",
            "test: add a case": "none",
            "ci: run on Linux": "none",
            "chore: tidy": "none",
            "style: format": "none",
            "feat!: drop the old flag": "major",
            "fix(cli)!: rename a flag": "major",
            "docs: explain\n\nBREAKING CHANGE: the flag is gone": "major",
            "Update the README": "patch",
            "Merge stuff from somewhere": "patch",
            "fix: a\n\nBREAKING CHANGE:\nthe flag is gone": "major",
            "Add stuff (#12)\n\n* feat!: drop the api\n* docs: note": "major",
            "Add stuff (#12)\n\n* fix: a\n* feat: b": "minor",
            "docs: notes (#3)\n\n* docs: a\n* test: b": "none",
            "docs: notes\n\n- update the readme": "none",
            "Add stuff (#12)\n\n* BREAKING CHANGE: gone": "major",
            "chore: tidy\n\n- Removed: the old copies": "none",
            "chore: tidy\n\n- Added: a page\n* Fixed(cli)!: a crash\n- Note: none": "none",
            "chore: tidy\n\n- Fix: a crash\n- FEAT: a page": "none",
            "chore: tidy\n\n- fixes: a crash\n- features: a page": "none",
            "chore: tidy (#4)\n\n* fix: stop a crash": "patch",
            "chore: tidy (#4)\n\n- fix(cli): stop a crash": "patch",
            "chore: tidy (#4)\n\n  * build: pin uv\n  * revert: undo a page": "patch",
            "chore: tidy (#4)\n\n* feat!: drop the api": "major",
            "chore: tidy (#4)\n\n* refactor(core)!: drop the api": "major",
            "docs: notes (#5)\n\n* feat(ui): add a page": "minor",
            "chore: x\n\n* fix(a\nb): c": "none",
            "chore: x\n\n* fix(a\n* feat: b): c": "minor",
            "docs: notes (#5)\n\n- Removed: a page\n- BREAKING CHANGE: the page is gone": "major",
        }
        for message, level in cases.items():
            with self.subTest(message=message):
                self.assertEqual(release_tag.commit_level(message), level)

    def test_a_breaking_change_below_one_raises_minor(self) -> None:
        self.assertEqual(release_tag.bump((0, 3, 2), "major"), (0, 4, 0))
        self.assertEqual(release_tag.bump((1, 3, 2), "major"), (2, 0, 0))
        self.assertEqual(release_tag.bump((1, 3, 2), "minor"), (1, 4, 0))
        self.assertEqual(release_tag.bump((1, 3, 2), "patch"), (1, 3, 3))


class ReleaseBase(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="release-tag-")
        self.addCleanup(scratch.cleanup)
        self.base = base = Path(scratch.name).resolve()
        self.origin, self.repo = base / "origin.git", base / "repo"
        git("init", "-q", "--bare", str(self.origin), cwd=base)
        self.repo.mkdir()
        git("init", "-q", "-b", "main", cwd=self.repo)
        for key, value in (("user.name", "t"), ("user.email", "t@example.com"), ("commit.gpgsign", "false"),
                           ("tag.gpgsign", "false"), ("maintenance.auto", "false"), ("gc.auto", "0")):
            git("config", key, value, cwd=self.repo)
        git("remote", "add", "origin", str(self.origin), cwd=self.repo)
        self.count = 0

    def commit(self, message: str) -> str:
        self.count += 1
        (self.repo / f"f{self.count}.txt").write_text(message)
        git("add", ".", cwd=self.repo)
        git("commit", "-q", "-m", message, cwd=self.repo)
        return git("rev-parse", "HEAD", cwd=self.repo).strip()

    def tag(self, name: str) -> None:
        git("tag", "-a", name, "-m", name, cwd=self.repo)
        git("push", "-q", "origin", f"refs/tags/{name}", cwd=self.repo)

    def profile(self, version: str = "", exit_code: int = 0) -> None:
        """A stub profile py whose recipe py::version prints VERSION, or exits with exit_code."""
        (self.repo / ".agents").mkdir(exist_ok=True)
        (self.repo / ".agents/stack.json").write_text(json.dumps({"version": 2, "profiles": ["py"]}))
        (self.repo / "Justfile").write_text("mod py 'prof.just'\n")
        body = f"    @exit {exit_code}\n" if exit_code else "    @cat VERSION\n"
        (self.repo / "prof.just").write_text("version:\n" + body)
        (self.repo / "VERSION").write_text(version + ("\n" if version else ""))

    def run_script(self, *args: str, message: Optional[Path] = None, **extra: str) -> subprocess.CompletedProcess:
        """Run the script. A hook gets GIT_EDITOR=: from git when git runs no editor, so pass GIT_EDITOR=":" for a
        message of git commit -m."""
        env = {k: v for k, v in os.environ.items() if not k.startswith("JN_RELEASE")}
        env.pop("GIT_DIR", None)
        env.pop("GIT_EDITOR", None)
        env.update(extra)
        if message is not None:
            env[release_tag.MESSAGE_VARIABLE] = str(message)
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.repo, env=env, capture_output=True,
                              text=True)

    def remote_tags(self) -> str:
        return git("ls-remote", "--tags", "origin", cwd=self.repo)


class ReleaseTests(ReleaseBase):
    def test_no_tag_yet_gives_v0_1_0(self) -> None:
        self.commit("docs: start")
        result = self.run_script("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("next tag: v0.1.0 (no tag yet)", result.stdout)

    def test_a_dry_run_changes_nothing(self) -> None:
        self.commit("feat: start")
        self.run_script("--dry-run")
        self.assertEqual(git("tag", "--list", cwd=self.repo), "")
        self.assertEqual(self.remote_tags(), "")

    def test_each_bump_since_the_last_tag(self) -> None:
        cases = [
            (["fix: a"], "v1.2.4"),
            (["feat: a", "fix: b"], "v1.3.0"),
            (["fix: a", "feat!: b"], "v2.0.0"),
            (["refactor: a\n\nBREAKING CHANGE: gone"], "v2.0.0"),
            (["A message that is not conventional"], "v1.2.4"),
        ]
        for messages, expected in cases:
            with self.subTest(messages=messages):
                self.setUp()
                self.commit("feat: start")
                self.tag("v1.2.3")
                for message in messages:
                    self.commit(message)
                result = self.run_script("--dry-run")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"next tag: {expected}", result.stdout)

    def test_a_breaking_change_below_one_raises_minor(self) -> None:
        self.commit("feat: start")
        self.tag("v0.4.1")
        self.commit("feat!: drop the flag")
        self.assertIn("next tag: v0.5.0", self.run_script("--dry-run").stdout)

    def test_docs_and_ci_only_give_no_release(self) -> None:
        self.commit("feat: start")
        self.tag("v0.1.0")
        for message in ("docs: a", "test: b", "ci: c", "chore: d", "style: e"):
            self.commit(message)
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no release", result.stdout)
        self.assertNotIn("v0.1.1", self.remote_tags())

    def test_merge_commits_do_not_count(self) -> None:
        self.commit("feat: start")
        self.tag("v0.1.0")
        git("switch", "-q", "-c", "topic", cwd=self.repo)
        self.commit("docs: a")
        git("switch", "-q", "main", cwd=self.repo)
        git("merge", "-q", "--no-ff", "-m", "Merge pull request #1 from topic", "topic", cwd=self.repo)
        self.assertIn("no release", self.run_script("--dry-run").stdout)

    def test_the_tag_is_annotated_pushed_and_checked(self) -> None:
        self.commit("feat: start")
        self.tag("v0.1.0")
        head = self.commit("fix: a")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("tagged v0.1.1", result.stdout)
        self.assertEqual(git("cat-file", "-t", "v0.1.1", cwd=self.repo).strip(), "tag")
        remote = git("ls-remote", "origin", "refs/tags/v0.1.1^{}", cwd=self.repo).split()
        self.assertEqual(remote[0], head)
        again = self.run_script()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("no release", again.stdout)

    def test_a_tag_on_another_commit_is_never_moved(self) -> None:
        self.commit("feat: start")
        self.tag("v0.1.0")
        git("switch", "-q", "-c", "other", cwd=self.repo)
        other = self.commit("fix: elsewhere")
        self.tag("v0.1.1")
        git("switch", "-q", "main", cwd=self.repo)
        self.commit("fix: here")
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn("v0.1.1 already exists", result.stderr)
        self.assertEqual(git("rev-parse", "v0.1.1^{commit}", cwd=self.repo).strip(), other)

    def test_an_older_commit_after_a_newer_release_gives_no_release(self) -> None:
        self.commit("feat: start")
        self.tag("v0.1.0")
        older = self.commit("fix: a")
        self.commit("feat: b")
        self.tag("v0.2.0")
        git("switch", "-q", "--detach", older, cwd=self.repo)
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no release: v0.2.0 is on a later commit", result.stdout)
        self.assertNotIn("v0.1.1", self.remote_tags())

    def test_a_remote_tag_on_another_commit_stops_the_release(self) -> None:
        self.commit("feat: start")
        self.tag("v0.1.0")
        self.commit("fix: a")
        git("tag", "-d", "v0.1.0", cwd=self.repo)
        git("tag", "-a", "v0.1.0", "-m", "v0.1.0", cwd=self.repo)
        result = self.run_script("--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("point at other commits", result.stderr)

    def test_a_shallow_checkout_stops_the_release(self) -> None:
        self.commit("feat: start")
        self.commit("fix: a")
        git("push", "-q", "origin", "main", cwd=self.repo)
        shallow = self.repo.parent / "shallow"
        git("clone", "-q", "--depth", "1", "-b", "main", f"file://{self.origin}", str(shallow), cwd=self.repo.parent)
        result = subprocess.run([sys.executable, str(SCRIPT), "--dry-run"], cwd=shallow, capture_output=True,
                                text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("shallow", result.stderr)

    def test_the_check_passes_a_shallow_checkout_and_says_so(self) -> None:
        self.commit("feat: start")
        self.commit("fix: a")
        git("push", "-q", "origin", "main", cwd=self.repo)
        shallow = self.repo.parent / "shallow"
        git("clone", "-q", "--depth", "1", "-b", "main", f"file://{self.origin}", str(shallow), cwd=self.repo.parent)
        result = subprocess.run([sys.executable, str(SCRIPT), "--check"], cwd=shallow, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("shallow", result.stdout)

    def test_the_check_passes_with_no_commit_and_with_no_tag(self) -> None:
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no commit yet", result.stdout)
        self.commit("feat: start")
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no release tag in this checkout", result.stdout)

    def test_the_check_on_a_merge_commit(self) -> None:
        self.commit("feat: start")
        self.tag("v0.1.0")
        git("switch", "-q", "-c", "topic", cwd=self.repo)
        self.commit("feat: a")
        git("switch", "-q", "main", cwd=self.repo)
        self.commit("docs: b")
        git("merge", "-q", "--no-ff", "-m", "Merge topic", "topic", cwd=self.repo)
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("the next tag is v0.2.0", result.stdout)

    def test_the_check_ignores_the_remote_and_tags_elsewhere(self) -> None:
        self.commit("feat: start")
        self.tag("v0.1.0")
        git("switch", "-q", "-c", "other", cwd=self.repo)
        self.commit("fix: elsewhere")
        self.tag("v0.1.1")
        git("switch", "-q", "main", cwd=self.repo)
        self.commit("fix: here")
        git("remote", "set-url", "origin", "/nonexistent/origin.git", cwd=self.repo)
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("release-check: the next tag is v0.1.1", result.stdout)

    def test_a_remote_tag_missing_here_stops_the_release(self) -> None:
        self.commit("feat: start")
        self.tag("v0.1.0")
        git("tag", "-d", "v0.1.0", cwd=self.repo)
        self.commit("fix: a")
        result = self.run_script("--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("git fetch --tags origin", result.stderr)


@unittest.skipUnless(shutil.which("just"), "needs just")
class ProfileVersionTests(ReleaseBase):
    """The cases with a version from the stub recipe py::version."""

    def test_no_tag_yet_uses_the_version(self) -> None:
        self.profile("0.3.0")
        self.commit("docs: start")
        result = self.run_script("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("next tag: v0.3.0", result.stdout)

    def test_the_tag_is_the_version(self) -> None:
        self.profile("1.0.0")
        self.commit("feat: start")
        self.tag("v1.0.0")
        (self.repo / "VERSION").write_text("1.1.0\n")
        self.commit("feat: a page")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("tagged v1.1.0", result.stdout)

    def test_a_higher_version_than_asked_is_allowed(self) -> None:
        self.profile("1.0.0")
        self.commit("feat: start")
        self.tag("v1.0.0")
        (self.repo / "VERSION").write_text("2.0.0\n")
        self.commit("fix: a")
        self.assertIn("next tag: v2.0.0", self.run_script("--dry-run").stdout)

    def test_a_version_below_the_bump_fails(self) -> None:
        self.profile("1.0.0")
        self.commit("feat: start")
        self.tag("v1.0.0")
        (self.repo / "VERSION").write_text("1.0.1\n")
        self.commit("feat: a page")
        result = self.run_script("--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("at least 1.1.0", result.stderr)

    def test_an_unchanged_version_with_a_fix_fails(self) -> None:
        self.profile("1.0.0")
        self.commit("feat: start")
        self.tag("v1.0.0")
        self.commit("fix: a")
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Raise the version", result.stderr)

    def test_a_version_lower_than_the_tag_fails(self) -> None:
        self.profile("0.9.0")
        self.commit("feat: start")
        self.tag("v1.0.0")
        self.commit("docs: a")
        result = self.run_script("--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("lower than the last tag v1.0.0", result.stderr)

    def test_a_tag_that_exists_gives_no_release(self) -> None:
        self.profile("1.0.0")
        self.commit("feat: start")
        self.tag("v1.0.0")
        self.commit("docs: a")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no release", result.stdout)

    def test_no_version_uses_the_commit_rule(self) -> None:
        self.profile("")
        self.commit("feat: start")
        self.tag("v1.0.0")
        self.commit("feat: a")
        self.assertIn("next tag: v1.1.0", self.run_script("--dry-run").stdout)

    def test_a_manifest_that_cannot_be_read_fails(self) -> None:
        self.profile(exit_code=2)
        self.commit("feat: start")
        result = self.run_script("--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot read the manifest", result.stderr)

    def test_a_profile_without_the_recipe_gives_no_version(self) -> None:
        self.profile("5.0.0")
        (self.repo / "prof.just").write_text("other:\n    @true\n")
        self.commit("feat: start")
        self.assertIn("next tag: v0.1.0", self.run_script("--dry-run").stdout)

    def test_the_check_fails_on_a_version_below_the_bump_without_a_remote(self) -> None:
        self.profile("1.0.0")
        self.commit("feat: start")
        self.tag("v1.0.0")
        git("remote", "remove", "origin", cwd=self.repo)
        self.commit("feat: a page")
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("at least 1.1.0", result.stderr)
        (self.repo / "VERSION").write_text("1.1.0\n")
        self.commit("chore: raise the version")
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("release-check: the next tag is v1.1.0", result.stdout)

    def test_the_check_fails_on_a_fix_with_the_tagged_version(self) -> None:
        self.profile("0.2.2")
        self.commit("feat: start")
        self.tag("v0.2.2")
        self.commit("fix: a bug")
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("must be at least 0.2.3, but the profile py gives 0.2.2", result.stderr)
        (self.repo / "VERSION").write_text("0.2.3\n")
        self.commit("chore: raise the version to 0.2.3")
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("release-check: the next tag is v0.2.3", result.stdout)

    def test_the_check_passes_chores_with_the_tagged_version(self) -> None:
        self.profile("0.2.2")
        self.commit("feat: start")
        self.tag("v0.2.2")
        self.commit("chore: a")
        self.commit("docs: b")
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("release-check: no release", result.stdout)

    def check_with_message(self, message: str, **extra: str) -> subprocess.CompletedProcess:
        """The check at the commit-msg hook: the message of the commit being made is in a file."""
        path = self.base / "COMMIT_EDITMSG"
        path.write_text(message)
        return self.run_script("--check", message=path, **extra)

    def test_the_check_counts_the_message_of_the_commit_being_made(self) -> None:
        self.profile("0.2.2")
        self.commit("feat: start")
        self.tag("v0.2.2")
        self.commit("chore: a")
        result = self.check_with_message("fix: a bug\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("1 commit(s) since v0.2.2 and the commit being made ask for patch, so the version must be at "
                      "least 0.2.3, but the profile py gives 0.2.2", result.stderr)
        (self.repo / "VERSION").write_text("0.2.3\n")
        result = self.check_with_message("fix: a bug\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("release-check: the next tag is v0.2.3", result.stdout)

    def test_the_check_passes_a_chore_message_with_the_tagged_version(self) -> None:
        self.profile("0.2.2")
        self.commit("feat: start")
        self.tag("v0.2.2")
        result = self.check_with_message("chore: a\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("and the commit being made ask for none", result.stdout)

    def test_the_message_leaves_out_comments_and_the_diff_of_verbose(self) -> None:
        self.profile("0.2.2")
        self.commit("feat: start")
        self.tag("v0.2.2")
        message = ("chore: a\n\n# Please enter the commit message\n# BREAKING CHANGE: a comment\n"
                   "# ------------------------ >8 ------------------------\n"
                   "diff --git a/CHANGELOG.md b/CHANGELOG.md\n - feat!: an old line of the file\n")
        result = self.check_with_message(message)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ask for none", result.stdout)

    def test_a_subject_that_starts_with_a_comment_character_counts(self) -> None:
        # git commit -m keeps the line, so the commit is not conventional and asks for a patch.
        self.profile("0.2.2")
        self.commit("feat: start")
        self.tag("v0.2.2")
        result = self.check_with_message("#12 fix login\n", GIT_EDITOR=":")
        self.assertEqual(result.returncode, 1)
        self.assertIn("at least 0.2.3", result.stderr)

    def test_a_custom_comment_character_cuts_the_diff_of_verbose(self) -> None:
        self.profile("0.2.2")
        self.commit("feat: start")
        self.tag("v0.2.2")
        git("config", "core.commentChar", ";", cwd=self.repo)
        message = ("chore: a\n\n; Please enter the commit message\n"
                   "; ------------------------ >8 ------------------------\n"
                   "diff --git a/N.md b/N.md\n BREAKING CHANGE: an old line\n - feat: another\n")
        result = self.check_with_message(message)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ask for none", result.stdout)

    def test_an_amend_replaces_the_message_of_head(self) -> None:
        self.profile("0.2.2")
        self.commit("feat: start")
        self.tag("v0.2.2")
        self.commit("fix: q")
        path = self.base / "COMMIT_EDITMSG"
        path.write_text("chore: q\n")
        env = dict(os.environ, **{release_tag.MESSAGE_VARIABLE: str(path), release_tag.AMEND_VARIABLE: "1"})
        env.pop("GIT_DIR", None)
        result = subprocess.run([sys.executable, str(SCRIPT), "--check"], cwd=self.repo, env=env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0 commit(s) since v0.2.2 and the commit being made ask for none", result.stdout)
        # Without the amend, HEAD counts too.
        self.assertEqual(self.check_with_message("chore: q\n").returncode, 1)

    def test_comment_lines_before_the_subject_do_not_count(self) -> None:
        # A commit template puts comment lines first, and git strips them after the editor.
        self.profile("0.2.2")
        self.commit("feat: start")
        self.tag("v0.2.2")
        result = self.check_with_message("# <type>(<scope>): <subject>\n# types: feat fix\n\ndocs: a note\n"
                                         "# Please enter the commit message for your changes.\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ask for none", result.stdout)

    def test_a_comment_subject_without_an_editor_counts(self) -> None:
        # git commit -m "#12 login" -m "docs: note" keeps the first line, which is not conventional.
        self.profile("0.2.2")
        self.commit("feat: start")
        self.tag("v0.2.2")
        result = self.check_with_message("#12 login\n\ndocs: note\n", GIT_EDITOR=":")
        self.assertEqual(result.returncode, 1)
        self.assertIn("at least 0.2.3", result.stderr)

    def test_the_cleanup_mode_decides_which_comment_lines_count(self) -> None:
        self.profile("0.2.2")
        self.commit("feat: start")
        self.tag("v0.2.2")
        message = "#12 fix\n\ndocs: g\n"
        cases = [({"JN_RELEASE_CLEANUP": "strip", "GIT_EDITOR": ":"}, 0),
                 ({"JN_RELEASE_CLEANUP": "scissors"}, 1),
                 ({"JN_RELEASE_CLEANUP": "verbatim"}, 1),
                 ({"JN_RELEASE_CLEANUP": "whitespace"}, 1),
                 ({"JN_RELEASE_CLEANUP": "default"}, 0),
                 ({"JN_RELEASE_CLEANUP": "default", "GIT_EDITOR": ":"}, 1),
                 # Unknown: each mode may apply, and the biggest bump counts.
                 ({"JN_RELEASE_CLEANUP": "unknown"}, 1)]
        for extra, code in cases:
            with self.subTest(extra=extra):
                self.assertEqual(self.check_with_message(message, **extra).returncode, code)
        # The biggest bump also when the comment lines hide it: strip gives the feat.
        result = self.check_with_message("#12 fix\n\nfeat: g\n", JN_RELEASE_CLEANUP="unknown")
        self.assertIn("at least 0.3.0", result.stderr)
        git("config", "commit.cleanup", "strip", cwd=self.repo)
        self.assertEqual(self.check_with_message(message, GIT_EDITOR=":").returncode, 0)

    def test_an_empty_message_counts_as_no_commit(self) -> None:
        self.profile("0.2.2")
        self.commit("feat: start")
        self.tag("v0.2.2")
        result = self.check_with_message("\n  \n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0 commit(s) since v0.2.2 ask for none", result.stdout)

    def test_a_message_file_that_is_missing_fails(self) -> None:
        self.profile("0.2.2")
        self.commit("feat: start")
        self.tag("v0.2.2")
        result = self.run_script("--check", message=self.base / "missing")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot be read", result.stderr)

    def test_the_release_ignores_the_message_variable(self) -> None:
        self.profile("0.2.2")
        self.commit("feat: start")
        self.tag("v0.2.2")
        self.commit("chore: a")
        result = self.run_script("--dry-run", message=self.base / "missing")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no release", result.stdout)

    def test_the_check_passes_a_chore_with_labelled_bullets(self) -> None:
        self.profile("1.0.0")
        self.commit("feat: start")
        self.tag("v1.0.0")
        self.commit("chore: drop the old copies\n\n- Removed: the old copies\n- Kept: the new copy")
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ask for none", result.stdout)

    def test_the_check_passes_a_tagged_version_with_docs_only(self) -> None:
        self.profile("1.0.0")
        self.commit("feat: start")
        self.tag("v1.0.0")
        self.commit("docs: a")
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("release-check: no release", result.stdout)

    def test_the_check_fails_on_a_version_below_the_tag(self) -> None:
        self.profile("0.9.0")
        self.commit("feat: start")
        self.tag("v1.0.0")
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("lower than the last tag", result.stderr)

    def test_the_check_fails_when_profiles_disagree(self) -> None:
        self.profile("1.0.0")
        (self.repo / ".agents/stack.json").write_text(json.dumps({"profiles": ["py", "ts"]}))
        (self.repo / "Justfile").write_text("mod py 'prof.just'\nmod ts 'ts.just'\n")
        (self.repo / "ts.just").write_text("version:\n    @echo 1.1.0\n")
        self.commit("feat: start")
        self.assertEqual(self.run_script("--check").returncode, 1)

    def test_two_profiles_that_disagree_fail(self) -> None:
        self.profile("1.0.0")
        (self.repo / ".agents/stack.json").write_text(json.dumps({"profiles": ["py", "ts"]}))
        (self.repo / "Justfile").write_text("mod py 'prof.just'\nmod ts 'ts.just'\n")
        (self.repo / "ts.just").write_text("version:\n    @echo 1.1.0\n")
        self.commit("feat: start")
        result = self.run_script("--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("different versions", result.stderr)


class HookTests(ReleaseBase):
    """A plain commit-msg hook that runs the check with the message file, as the commit gate does, in real commits."""

    def setUp(self) -> None:
        super().setUp()
        hook = self.repo / ".git/hooks/commit-msg"
        hook.write_text(f'#!/bin/sh\n{release_tag.MESSAGE_VARIABLE}="$1" exec "{sys.executable}" "{SCRIPT}" --check\n')
        hook.chmod(0o755)
        self.profile("0.2.2")
        self.commit("feat: start")
        self.tag("v0.2.2")

    def run_git(self, *args: str, **extra: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and not k.startswith("JN_RELEASE")}
        env.update(extra)
        return subprocess.run(["git", *args], cwd=self.repo, env=env, capture_output=True, text=True)

    def test_a_merge_of_chores_with_the_tagged_version_goes_through(self) -> None:
        git("checkout", "-q", "-b", "side", cwd=self.repo)
        self.commit("chore: b")
        git("checkout", "-q", "main", cwd=self.repo)
        self.commit("chore: a")
        result = self.run_git("merge", "-q", "--no-ff", "-m", "Merge branch 'side'", "side")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(git("log", "-1", "--format=%P", cwd=self.repo).split()), 2)
        # An amend of the merge is a merge too, and the release skips it.
        result = self.run_git("commit", "-q", "--amend", "-m", "Merge side", **{release_tag.AMEND_VARIABLE: "1"})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_maybe_amend_on_a_merge_counts_the_message(self) -> None:
        git("checkout", "-q", "-b", "side", cwd=self.repo)
        self.commit("chore: b")
        git("checkout", "-q", "main", cwd=self.repo)
        self.commit("chore: a")
        self.assertEqual(self.run_git("merge", "-q", "--no-ff", "-m", "Merge side", "side").returncode, 0)
        (self.repo / "n.txt").write_text("n\n")
        git("add", "n.txt", cwd=self.repo)
        result = self.run_git("commit", "-q", "-m", "fix: use --amend", **{release_tag.AMEND_VARIABLE: "maybe"})
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("at least 0.2.3", result.stderr)

    def test_a_merge_with_a_conflict_goes_through(self) -> None:
        git("checkout", "-q", "-b", "side", cwd=self.repo)
        (self.repo / "c.txt").write_text("side\n")
        git("add", "c.txt", cwd=self.repo)
        git("commit", "-q", "--no-verify", "-m", "chore: b", cwd=self.repo)
        git("checkout", "-q", "main", cwd=self.repo)
        (self.repo / "c.txt").write_text("main\n")
        git("add", "c.txt", cwd=self.repo)
        git("commit", "-q", "--no-verify", "-m", "chore: a", cwd=self.repo)
        self.assertNotEqual(self.run_git("merge", "-q", "side").returncode, 0)
        (self.repo / "c.txt").write_text("both\n")
        git("add", "c.txt", cwd=self.repo)
        result = self.run_git("commit", "-q", "--no-edit")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_comment_char_auto_keeps_a_subject_that_git_keeps(self) -> None:
        # With auto, git picks a character that starts no line, so it keeps "#12 tidy", which asks for a patch.
        git("config", "core.commentChar", "auto", cwd=self.repo)
        (self.repo / "n.txt").write_text("n\n")
        git("add", "n.txt", cwd=self.repo)
        result = self.run_git("commit", "-q", "-e", "-m", "#12 tidy", "-m", "docs: x", GIT_EDITOR="true")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("at least 0.2.3", result.stderr)
        result = self.run_git("commit", "-q", "--no-verify", "-e", "-m", "#12 tidy", "-m", "docs: x", GIT_EDITOR="true")
        self.assertEqual(git("log", "-1", "--format=%s", cwd=self.repo).strip(), "#12 tidy")

    def test_a_scissors_line_of_a_file_without_an_editor_is_kept(self) -> None:
        # Without an editor and -v, git keeps the lines after a scissors line of the file, and the bullet counts.
        (self.base / "m").write_text("docs: notes\n\n# ------------------------ >8 ------------------------\n"
                                     "- fix: y\n")
        (self.repo / "n.txt").write_text("n\n")
        git("add", "n.txt", cwd=self.repo)
        result = self.run_git("commit", "-q", "-F", str(self.base / "m"))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("at least 0.2.3", result.stderr)

    def test_an_amend_of_the_tagged_commit_stops_with_a_clear_message(self) -> None:
        result = self.run_git("commit", "-q", "--amend", "-m", "feat: retag", **{release_tag.AMEND_VARIABLE: "1"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("HEAD is the release v0.2.2", result.stderr)
        self.assertEqual(git("tag", "--points-at", "HEAD", cwd=self.repo).split(), ["v0.2.2"])
        # A new commit on the tagged HEAD is no amend, and the check counts it.
        (self.repo / "n.txt").write_text("n\n")
        git("add", "n.txt", cwd=self.repo)
        result = self.run_git("commit", "-q", "-m", "docs: n")
        self.assertEqual(result.returncode, 0, result.stderr)


class WorkflowTests(unittest.TestCase):
    """The release jobs run just release after the check, with write access to push the tag, and no agent."""

    def test_the_release_job_of_this_repository(self) -> None:
        text = (ROOT / ".github/workflows/verify.yml").read_text()
        job = text[text.index("\n  release:\n"):]
        for line in ("needs: verify", "if: github.event_name == 'push' && github.ref == 'refs/heads/main'",
                     "contents: write", "fetch-depth: 0", "run: just release"):
            with self.subTest(line=line):
                self.assertIn(line, job)

    def test_the_release_starter(self) -> None:
        text = (ROOT / ".agents/skills/gsu/assets/templates/github-release.yml").read_text()
        head, job = text.split("\n  release:\n")
        self.assertIn("branches: [main]", head)
        self.assertIn("run: just check", head)
        self.assertNotIn("concurrency", head, "a workflow-wide group cancels the check of a pending push")
        for line in ("needs: check", "contents: write", "group: release", "fetch-depth: 0", "run: just release"):
            with self.subTest(line=line):
                self.assertIn(line, job)

    def test_ci_gets_the_release_check_only_through_just_check(self) -> None:
        text = (ROOT / ".agents/skills/gsu/assets/templates/github-check.yml").read_text()
        self.assertNotIn("just release", text)
        self.assertIn("fetch-depth: 0", text)
        role = (ROOT / ".agents/just/roles/agent_gest_git_skills.just").read_text()
        recipe = role[role.index("\nrelease-check:\n"):]
        self.assertIn("release_tag.py --check", recipe)
        self.assertIn("jlog step release-check", recipe)


if __name__ == "__main__":
    unittest.main()
