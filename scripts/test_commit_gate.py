"""Check the commit gate of gcm in scratch repositories, with the gate installed as the git hooks."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/gcm/scripts/commit_gate.py"

spec = importlib.util.spec_from_file_location("commit_gate", SCRIPT)
commit_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(commit_gate)

JUSTFILE = """\
check:
    exit 1
lint:
    true
review:
    true
test-review:
    true
update-docs:
    true
prose:
    true
security:
    true
"""

STACK = {"steps": ["lint"], "code": {"python": ["**/*.py"]}}
# The page rule of a nossaifd checkout, from NOSSAIFD_DIR, for the test with the real rule.
NOSSAIFD_RULE = (Path(os.environ.get("NOSSAIFD_DIR", Path.home() / "Projects/nossaifd"))
                 / ".agents/skills/nossaifd/scripts/prose_gate.py")


def git(*args: str, cwd: Path, env=None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=check, capture_output=True, text=True)


@unittest.skipUnless(shutil.which("just"), "needs just")
class GateTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="commit-gate-test-")
        self.addCleanup(scratch.cleanup)
        self.base = Path(scratch.name).resolve()
        self.repo = self.base / "proj"
        self.repo.mkdir()
        # PRE_COMMIT is set when the suite runs inside a hook of the pre-commit framework.
        self.person = {k: v for k, v in os.environ.items()
                       if k not in commit_gate.AGENT_VARIABLES and not k.startswith("GIT_") and k != "PRE_COMMIT"}
        self.person.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
                           GIT_COMMITTER_EMAIL="t@example.com")
        self.agent = dict(self.person, CLAUDE_CODE_SESSION_ID="session-1")
        git("init", "-q", "-b", "main", cwd=self.repo)
        for hook in ("pre-commit", "pre-merge-commit", "commit-msg"):
            path = self.repo / ".git/hooks" / hook
            path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{SCRIPT}" --hook {hook} "$@"\n')
            path.chmod(0o755)
        (self.repo / "Justfile").write_text(JUSTFILE)
        self.write(".agents/stack.json", json.dumps(STACK))
        log = self.repo / ".agents/log"
        (log / "records").mkdir(parents=True)
        (log / ".gitignore").write_text("*\n")
        self.count = 0

    def write(self, path: str, text: str) -> None:
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def tree(self) -> str:
        return commit_gate.worktree_tree(self.repo)

    def passed(self, tree=None, steps=("lint",)) -> None:
        line = {"kind": "pass", "tree": tree or self.tree(), "steps": list(steps)}
        with (self.repo / ".agents/log/just.jsonl").open("a") as log:
            log.write(json.dumps(line) + "\n")

    def record(self, target: str, start=None, end=None, **fields) -> None:
        tree = self.tree()
        self.count += 1
        record = {"version": 1, "target": target, "status": "success", "input_tree": start or tree,
                  "output_tree": end or start or tree, "findings": [], "source": "hook"}
        record.update(fields)
        (self.repo / f".agents/log/records/{self.count}.json").write_text(json.dumps(record))

    def commit(self, *args: str, env=None) -> subprocess.CompletedProcess:
        return git("commit", "-q", "-m", "x", *args, cwd=self.repo, env=env or self.person, check=False)

    def first_commit(self) -> None:
        """A first commit by a person, so that the tests after it have a parent."""
        git("add", "-A", cwd=self.repo)
        self.passed()
        result = self.commit()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_repository_path_with_a_colon_or_a_quote_has_its_tree(self) -> None:
        # Git splits GIT_ALTERNATE_OBJECT_DIRECTORIES at each colon, so the path of the object store goes in quotes.
        repo = self.base / 'we:ird"name'
        repo.mkdir()
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@example.com")
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True, env=env)
        (repo / ".gitignore").write_text("kept.txt\n")
        (repo / "kept.txt").write_text("kept\n")
        subprocess.run(["git", "add", ".gitignore"], cwd=repo, check=True, env=env)
        subprocess.run(["git", "add", "-f", "kept.txt"], cwd=repo, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=repo, check=True, env=env)
        # An entry that git assumes unchanged makes the gate start from HEAD, which needs the object store.
        subprocess.run(["git", "update-index", "--assume-unchanged", ".gitignore"], cwd=repo, check=True, env=env)
        head = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=repo, check=True, env=env,
                              capture_output=True, text=True).stdout.strip()
        self.assertEqual(commit_gate.worktree_tree(repo), head)

    def test_a_change_in_the_second_of_the_index_is_in_the_worktree_tree(self) -> None:
        # Git trusts the stat data of an entry only when the file is older than the index file. A copy of the index
        # with a new time would make a same-size change in that second look clean.
        # The ctime of a file cannot be set, so git must not compare it: a change of the ctime alone shows the change.
        git("config", "core.trustctime", "false", cwd=self.repo)
        index, path = self.repo / ".git/index", self.repo / "a.txt"
        self.write("a.txt", "aaa\n")
        # A time in the past, so that a copy made now is newer than the entry.
        stamp = path.stat().st_mtime_ns - 10 * 10**9
        os.utime(path, ns=(stamp, stamp))
        git("add", "-A", cwd=self.repo)
        # The index has the time of the file, so its entry is racy, and only its content tells the change.
        os.utime(index, ns=(stamp, stamp))
        before = commit_gate.worktree_tree(self.repo)
        self.write("a.txt", "bbb\n")
        os.utime(path, ns=(stamp, stamp))
        self.assertNotEqual(commit_gate.worktree_tree(self.repo), before)

    def test_a_split_index_leaves_no_new_shared_index(self) -> None:
        self.write("a.txt", "x\n")
        git("add", "-A", cwd=self.repo)
        git("config", "core.splitIndex", "true", cwd=self.repo)
        git("update-index", "--split-index", cwd=self.repo)
        before = sorted(p.name for p in (self.repo / ".git").glob("sharedindex.*"))
        self.write("a.txt", "y\n")
        self.write("b.txt", "z\n")
        commit_gate.worktree_tree(self.repo)
        self.assertEqual(sorted(p.name for p in (self.repo / ".git").glob("sharedindex.*")), before)

    def assertStops(self, result, text: str) -> None:
        self.assertNotEqual(result.returncode, 0, "the commit went through")
        self.assertIn(text, result.stderr)

    def assertGoes(self, result) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    # The pass

    def test_a_commit_with_no_pass_stops_and_says_run_just_check(self) -> None:
        git("add", "-A", cwd=self.repo)
        self.assertStops(self.commit(), "run `just check`")

    def test_the_gate_never_runs_a_step(self) -> None:
        # The check recipe exits with 1, so a gate that ran it would stop the commit.
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.assertGoes(self.commit())

    def test_a_pass_of_fewer_steps_than_the_stack_does_not_count(self) -> None:
        git("add", "-A", cwd=self.repo)
        self.passed(steps=())
        self.assertStops(self.commit(), "run `just check`")

    def test_a_pass_in_the_shared_log_folder_counts_in_a_worktree(self) -> None:
        self.first_commit()
        other = self.base / "wt"
        git("worktree", "add", "-q", "-b", "side", str(other), cwd=self.repo)
        (other / "a.txt").write_text("a\n")
        git("add", "-A", cwd=other)
        tree = commit_gate.worktree_tree(other)
        self.passed(tree)
        result = git("commit", "-q", "-m", "x", cwd=other, env=self.person, check=False)
        self.assertGoes(result)

    # The worktree tree

    def test_partial_staging_stops_with_the_stash_fix(self) -> None:
        self.first_commit()
        self.write("a.txt", "a\n")
        self.write("b.txt", "b\n")
        git("add", "a.txt", cwd=self.repo)
        self.passed()
        self.assertStops(self.commit(), "git stash --keep-index -u")

    def test_under_the_framework_partial_staging_still_gives_the_stash_fix(self) -> None:
        # pre-commit puts the unstaged edits of tracked files aside before its hooks run, as git stash --keep-index
        # does, so the gate sees a staged tree with no pass. It sets PRE_COMMIT=1, and then the stop names the stash
        # fix too.
        self.write("b.txt", "b\n")
        self.first_commit()
        self.write("a.txt", "a\n")
        self.write("b.txt", "b2\n")
        git("add", "a.txt", cwd=self.repo)
        self.passed()
        git("stash", "push", "-q", "--keep-index", cwd=self.repo, env=self.person)
        framework = dict(self.person, PRE_COMMIT="1")
        result = self.commit(env=framework)
        self.assertStops(result, "no pass of `just check` for this tree")
        self.assertIn("pre-commit put the rest aside", result.stderr)
        self.assertIn("git stash --keep-index -u", result.stderr)
        self.assertNotIn("pre-commit put the rest aside", self.commit().stderr)

    def test_commit_all_by_an_agent_stops_when_the_records_cover_only_the_staged_files(self) -> None:
        self.first_commit()
        self.write("a.txt", "a\n")
        git("add", "a.txt", cwd=self.repo)
        staged = git("write-tree", cwd=self.repo).stdout.strip()
        self.passed(staged)
        self.record("review", staged)
        self.write("README", "changed\n")
        git("add", "-N", "README", cwd=self.repo)
        result = self.commit("-a", env=self.agent)
        self.assertStops(result, "run `just check`")

    def test_the_worktree_tree_matches_jlog(self) -> None:
        if not shutil.which("jlog"):
            self.skipTest("needs jlog")
        self.first_commit()
        self.write("a.txt", "a\n")
        (self.repo / "Justfile").write_text('set shell := ["jlog", "sh", "-cu"]\n\nt:\n    true\n')
        subprocess.run(["just", "t"], cwd=self.repo, env=self.person, check=True, capture_output=True)
        lines = (self.repo / ".agents/log/just.jsonl").read_text().splitlines()
        trees = [json.loads(line)["tree"] for line in lines if json.loads(line).get("kind") == "tree"]
        self.assertEqual(trees[-1], self.tree())

    # The records of an agent

    def test_an_agent_commit_with_no_review_record_stops(self) -> None:
        self.first_commit()
        self.write("a.txt", "a\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.assertStops(self.commit(env=self.agent), "`just review`")
        self.record("review")
        self.assertGoes(self.commit(env=self.agent))

    def test_a_person_needs_no_record(self) -> None:
        self.first_commit()
        self.write("a.py", "x = 1\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.assertGoes(self.commit())

    def test_the_first_commit_works_with_the_default_list(self) -> None:
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("review")
        self.assertGoes(self.commit(env=self.agent))

    def test_a_code_change_needs_test_review(self) -> None:
        self.first_commit()
        self.write("a.py", "x = 1\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("review")
        self.assertStops(self.commit(env=self.agent), "`just test-review`")
        self.record("test-review")
        self.assertGoes(self.commit(env=self.agent))

    def test_the_chain_docs_prose_review_passes(self) -> None:
        self.first_commit()
        self.write("guide.md", "draft\n")
        t0 = self.tree()
        self.write("guide.md", "docs\n")
        t1 = self.tree()
        self.write("guide.md", "prose\n")
        t2 = self.tree()
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("update-docs", t0, t1)
        self.record("prose", t1, t2)
        self.record("review")
        self.assertGoes(self.commit(env=self.agent))

    # The pages

    RULE = "def is_page(rel):\n    return rel.endswith('.md') and not rel.endswith('CHANGELOG.md')\n"

    def change_only(self, path: str, text: str = "new\n") -> subprocess.CompletedProcess:
        """Commit a change of PATH alone, as an agent, with a pass and a review record but no other record."""
        self.write(path, text)
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("review")
        return self.commit(env=self.agent)

    def test_with_the_page_rule_a_changelog_alone_needs_no_prose(self) -> None:
        self.write(commit_gate.PAGE_RULE, self.RULE)
        self.first_commit()
        self.assertGoes(self.change_only("CHANGELOG.md"))
        # A page with a pass and a review, but no prose record, still stops.
        self.assertStops(self.change_only("guide.md"), "`just update-docs`, `just prose`")

    def test_without_the_page_rule_a_changelog_is_a_page(self) -> None:
        self.first_commit()
        self.assertStops(self.change_only("CHANGELOG.md"), "`just update-docs`, `just prose`")

    def test_the_page_rule_comes_from_the_parent(self) -> None:
        self.write(commit_gate.PAGE_RULE, self.RULE)
        self.first_commit()
        self.write(commit_gate.PAGE_RULE, "def is_page(rel):\n    return False\n")
        self.assertStops(self.change_only("guide.md"), "`just update-docs`, `just prose`")

    def test_a_page_rule_that_fails_stops_the_commit(self) -> None:
        cases = (
            ("def is_page(:\n", "fails in Python"),
            ("x = 1\n", "has no is_page"),
            ("def is_page(rel):\n    raise ValueError('bad rule')\n", "ValueError: bad rule"),
            # A rule that ends its Python, or that changes the environment, cannot let the page go.
            ("import sys\nsys.exit(0)\n", "ends before it checks each path"),
            ("import sys\ndef is_page(rel):\n    sys.exit(0)\n", "ends before it checks each path"),
            ("import os\nos.environ.clear()\ndef is_page(rel):\n    return False\n", None),
            ("import sys\ndef is_page(rel):\n    sys.__stdout__.buffer.write(b'other.md\\0')\n    return False\n",
             "names paths that the commit does not change"),
        )
        for text, message in cases:
            with self.subTest(text=text):
                self.setUp()
                self.write(commit_gate.PAGE_RULE, text)
                self.first_commit()
                if message:
                    self.assertStops(self.change_only("guide.md"), message)
                else:
                    # The rule says no file is a page, and the environment of the gate is as it was: the gate still
                    # asks for the other records.
                    self.write("tool.py", "x = 1\n")
                    self.assertStops(self.change_only("guide.md"), "`just test-review`")

    def test_a_rule_that_prints_still_gives_the_pages(self) -> None:
        self.write(commit_gate.PAGE_RULE, "print('loaded')\ndef is_page(rel):\n    print('checking', rel)\n"
                   "    return rel.endswith('.md') and not rel.endswith('CHANGELOG.md')\n")
        self.first_commit()
        self.assertGoes(self.change_only("CHANGELOG.md"))
        self.assertStops(self.change_only("guide.md"), "`just update-docs`, `just prose`")

    def test_a_page_whose_name_is_not_utf8_is_a_page(self) -> None:
        self.write(commit_gate.PAGE_RULE, self.RULE)
        self.first_commit()
        # git() keeps the bytes of such a name as surrogates. Some file systems refuse the name, so the rule gets it
        # straight.
        name = b"caf\xe9.md".decode(errors="surrogateescape")
        rule = commit_gate.page_rule(self.repo, git("rev-parse", "HEAD", cwd=self.repo).stdout.strip())
        self.assertEqual(rule([name, "tool.py", "CHANGELOG.md"]), [name])

    def test_the_first_commit_uses_the_globs(self) -> None:
        # The first commit has no parent, so its own rule cannot loosen the rule for its own pages.
        self.write(commit_gate.PAGE_RULE, "def is_page(rel):\n    return False\n")
        self.write("guide.md", "new\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("review")
        self.assertStops(self.commit(env=self.agent), "`just update-docs`, `just prose`")

    def test_a_generated_page_needs_no_prose(self) -> None:
        self.write(commit_gate.PAGE_RULE, self.RULE)
        self.write(".agents/generated.txt", "out/**\n")
        self.first_commit()
        self.assertGoes(self.change_only("out/api.md"))

    @unittest.skipUnless(NOSSAIFD_RULE.is_file(), "needs a nossaifd checkout in NOSSAIFD_DIR")
    def test_the_rule_of_nossaifd_skips_agents_md(self) -> None:
        self.write(commit_gate.PAGE_RULE, NOSSAIFD_RULE.read_text())
        self.first_commit()
        self.assertGoes(self.change_only("AGENTS.md"))
        self.assertGoes(self.change_only("CHANGELOG.md", "two\n"))
        self.assertStops(self.change_only("docs/guide.qmd"), "`just prose`")

    def test_the_same_records_in_another_order_stop(self) -> None:
        self.first_commit()
        self.write("guide.md", "draft\n")
        t0 = self.tree()
        self.write("guide.md", "prose\n")
        t1 = self.tree()
        self.write("guide.md", "docs\n")
        t2 = self.tree()
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("prose", t0, t1)
        self.record("update-docs", t1, t2)
        self.record("review")
        self.assertStops(self.commit(env=self.agent), "`just update-docs`, `just prose`")

    def test_test_review_then_review_passes(self) -> None:
        # test-review and review both check the last tree, in either order.
        self.first_commit()
        self.write("a.py", "x = 1\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("test-review")
        self.record("review")
        self.assertGoes(self.commit(env=self.agent))

    def test_a_test_review_before_the_last_change_does_not_count(self) -> None:
        self.first_commit()
        self.write("guide.md", "draft\n")
        t0 = self.tree()
        self.write("a.py", "x = 1\n")
        self.record("test-review")
        self.write("guide.md", "docs\n")
        t1 = self.tree()
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("update-docs", t0, t1)
        self.record("prose", t1, t1)
        self.record("review")
        self.assertStops(self.commit(env=self.agent), "`just test-review`")

    def test_a_review_before_the_last_change_does_not_count(self) -> None:
        self.first_commit()
        self.write("guide.md", "draft\n")
        t0 = self.tree()
        self.record("review")
        self.write("guide.md", "docs\n")
        t1 = self.tree()
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("update-docs", t0, t1)
        self.record("prose", t1, t1)
        self.assertStops(self.commit(env=self.agent), "`just review`")

    def test_a_failed_record_or_an_open_finding_does_not_count(self) -> None:
        self.first_commit()
        self.write("a.txt", "a\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("review", status="failed")
        self.record("review", findings=[{"summary": "a bug"}])
        self.record("review", findings=[{"summary": "a bug", "test": "  "}])
        self.assertStops(self.commit(env=self.agent), "`just review`")
        self.record("review", findings=[{"summary": "a bug", "test": "test_a"}, {"summary": "b", "reason": "ok"}])
        self.assertGoes(self.commit(env=self.agent))

    def test_a_skip_with_a_reason_counts_and_one_without_does_not(self) -> None:
        self.first_commit()
        self.write("a.txt", "a\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("review", source="skip", reason="  ")
        self.assertStops(self.commit(env=self.agent), "`just review`")
        self.record("review", source="skip", reason="a typo")
        self.assertGoes(self.commit(env=self.agent))

    # The lists come from the parent

    def test_an_empty_required_list_in_the_commit_does_not_remove_the_review(self) -> None:
        self.first_commit()
        self.write(".agents/targets/required.txt", "")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.assertStops(self.commit(env=self.agent), "`just review`")
        self.record("review")
        self.assertGoes(self.commit(env=self.agent))
        # The parent now has the empty list, and the review is still required.
        self.write("a.txt", "a\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.assertStops(self.commit(env=self.agent), "`just review`")

    def test_a_commit_that_removes_a_language_still_needs_test_review_for_its_code(self) -> None:
        self.first_commit()
        self.write(".agents/stack.json", json.dumps({"steps": ["lint"]}))
        self.write("a.py", "x = 1\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("review")
        self.assertStops(self.commit(env=self.agent), "`just test-review`")

    def test_a_generated_path_of_the_parent_needs_no_test_review(self) -> None:
        self.write(".agents/generated.txt", "gen/**\n")
        self.first_commit()
        self.write("gen/a.py", "x = 1\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("review")
        self.assertGoes(self.commit(env=self.agent))

    def test_a_deleted_page_needs_update_docs_and_prose(self) -> None:
        self.write("guide.md", "text\n")
        self.first_commit()
        (self.repo / "guide.md").unlink()
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("review")
        self.assertStops(self.commit(env=self.agent), "`just update-docs`, `just prose`")

    def test_a_required_list_that_the_commit_loosens_still_counts_as_the_parent_has_it(self) -> None:
        self.first_commit()
        self.write(".agents/targets/required.txt", "review **\n")
        self.write("a.py", "x = 1\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("review")
        self.assertStops(self.commit(env=self.agent), "`just test-review`")

    def test_a_generated_list_that_the_commit_adds_does_not_exempt_its_own_code(self) -> None:
        self.first_commit()
        self.write(".agents/generated.txt", "gen/**\n")
        self.write("gen/a.py", "x = 1\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("review")
        self.assertStops(self.commit(env=self.agent), "`just test-review`")

    def test_a_commit_that_removes_a_step_goes_through(self) -> None:
        self.first_commit()
        self.write(".agents/stack.json", json.dumps({"steps": [], "code": STACK["code"]}))
        (self.repo / "Justfile").write_text(JUSTFILE.replace("lint:\n    true\n", ""))
        git("add", "-A", cwd=self.repo)
        self.passed(steps=())
        self.assertGoes(self.commit())

    def test_the_commit_that_installs_the_gates_in_a_repository_with_history_goes_through(self) -> None:
        stack = self.repo / ".agents/stack.json"
        stack.rename(self.base / "stack.json")
        for hook in ("pre-commit", "pre-merge-commit", "commit-msg"):
            (self.repo / ".git/hooks" / hook).rename(self.base / hook)
        git("add", "-A", cwd=self.repo)
        self.assertGoes(self.commit())
        (self.base / "stack.json").rename(stack)
        for hook in ("pre-commit", "pre-merge-commit", "commit-msg"):
            (self.base / hook).rename(self.repo / ".git/hooks" / hook)
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("review")
        self.assertGoes(self.commit(env=self.agent))

    def test_an_amend_compares_with_the_parent_of_the_commit_it_replaces(self) -> None:
        self.first_commit()
        self.write("a.py", "x = 1\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("review")
        self.record("test-review")
        self.assertGoes(self.commit(env=self.agent))
        # The amend keeps a.py, so against its real parent it still adds code.
        self.write("notes.txt", "n\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("review")
        self.assertStops(self.commit("--amend", env=self.agent), "`just test-review`")
        self.assertStops(self.commit("--amen", env=self.agent), "`just test-review`")
        self.record("test-review")
        self.assertGoes(self.commit("--amend", env=self.agent))

    def test_an_amend_of_a_commit_that_loosened_the_list_uses_the_list_before_it(self) -> None:
        self.first_commit()
        self.write(".agents/targets/required.txt", "review **\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.assertGoes(self.commit())
        self.write("a.py", "x = 1\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("review")
        self.assertStops(self.commit("--amend", env=self.agent), "`just test-review`")

    def test_an_odd_line_in_the_required_list_cannot_land(self) -> None:
        self.first_commit()
        for line in ("review  **  # all\n", "test-review  :(top)x\n", "te$t  **\n"):
            with self.subTest(line=line):
                self.write(".agents/targets/required.txt", line)
                git("add", "-A", cwd=self.repo)
                self.passed()
                self.assertStops(self.commit(), "cannot read")

    def test_an_odd_list_in_the_parent_gives_way_to_the_default_list(self) -> None:
        self.first_commit()
        self.write(".agents/targets/required.txt", "review  **  # all\n")
        git("add", "-A", cwd=self.repo)
        git("commit", "-q", "-m", "old list", "--no-verify", cwd=self.repo, env=self.person)
        self.write(".agents/targets/required.txt", "review  **\n")
        self.write("a.py", "x = 1\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("review")
        result = self.commit(env=self.agent)
        self.assertStops(result, "`just test-review`")
        self.assertIn("uses the default list", result.stderr)
        self.record("test-review")
        self.assertGoes(self.commit(env=self.agent))

    def test_a_message_that_looks_like_amend_does_not_bring_back_looser_rules(self) -> None:
        self.first_commit()
        self.write(".agents/targets/required.txt", commit_gate.DEFAULT_REQUIRED + "security @code\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.assertGoes(self.commit())
        self.write("a.py", "x = 1\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.record("review")
        self.record("test-review")
        for message in ("--amend", "fix --amen"):
            with self.subTest(message=message):
                result = git("commit", "-q", "-m", message, cwd=self.repo, env=self.agent, check=False)
                self.assertStops(result, "`just security`")

    def test_a_commit_that_removes_the_stack_says_to_take_off_the_hooks(self) -> None:
        self.first_commit()
        (self.repo / ".agents/stack.json").unlink()
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.assertStops(self.commit(), "take off their hooks")

    def test_claudecode_alone_marks_an_agent(self) -> None:
        self.first_commit()
        self.write("a.txt", "a\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.assertStops(self.commit(env=dict(self.person, CLAUDECODE="1")), "`just review`")

    # The recipes

    def test_a_missing_recipe_stops_and_says_run_just_install(self) -> None:
        (self.repo / "Justfile").write_text("check:\n    true\nreview:\n    true\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.assertStops(self.commit(), "`lint`")

    # git merge

    def test_git_merge_runs_the_gate(self) -> None:
        self.first_commit()
        git("checkout", "-q", "-b", "side", cwd=self.repo)
        self.write("b.txt", "b\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.assertGoes(self.commit())
        git("checkout", "-q", "main", cwd=self.repo)
        self.write("a.txt", "a\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.assertGoes(self.commit())
        merge = ["merge", "-q", "--no-ff", "-m", "m", "side"]
        result = git(*merge, cwd=self.repo, env=self.person, check=False)
        self.assertStops(result, "run `just check`")
        # The stopped merge left the merged files in the worktree. Pass their tree, then merge again.
        self.passed()
        git("merge", "--abort", cwd=self.repo)
        self.assertGoes(git(*merge, cwd=self.repo, env=self.person, check=False))

    def trailers(self, base: str = "main~1", head: str = "HEAD") -> list:
        return commit_gate.check_trailers(self.repo, base, head)

    def change(self, name: str, text: str, *args: str) -> None:
        self.write(name, text)
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.assertGoes(self.commit(*args))

    def test_a_commit_through_the_gate_has_a_trailer_that_ci_accepts(self) -> None:
        self.first_commit()
        self.change("a.txt", "a\n")
        message = git("log", "-1", "--format=%B", cwd=self.repo).stdout
        self.assertIn("Commit-Gate: patch:", message)
        self.assertEqual(self.trailers(), [])
        # The first commit counts too, against the empty tree.
        first = git("rev-list", "--max-parents=0", "HEAD", cwd=self.repo).stdout.strip()
        self.assertEqual(commit_gate.commit_patch_id(self.repo, first) in git(
            "log", "-1", "--format=%B", first, cwd=self.repo).stdout, True)

    def test_the_range_comes_from_ci_then_the_push_then_the_upstream(self) -> None:
        self.first_commit()
        self.change("a.txt", "a\n")
        rng = lambda **env: commit_gate.ci_range(self.repo, env)  # noqa: E731
        # The push comes first, so a JN_CI_BASE in the shell does not change it.
        self.assertEqual(rng(JN_CI_BASE="b", JN_CI_HEAD="h", PRE_COMMIT_FROM_REF="f", PRE_COMMIT_TO_REF="t"),
                         ("f", "t"))
        self.assertEqual(rng(PRE_COMMIT_FROM_REF="f", PRE_COMMIT_TO_REF="t", PRE_COMMIT_LOCAL_BRANCH="l"), ("f", "t"))
        # A push of a new history: the remote has none of its commits, so each one counts.
        self.assertEqual(rng(JN_CI_BASE="b", PRE_COMMIT_LOCAL_BRANCH="refs/heads/main"), (None, "refs/heads/main"))
        self.assertEqual(rng(JN_CI_BASE="b", JN_CI_HEAD="h"), ("b", "h"))
        with self.assertRaisesRegex(commit_gate.Stop, "JN_CI_BASE"):
            rng()
        git("update-ref", "refs/remotes/origin/HEAD", "HEAD~1", cwd=self.repo)
        self.assertEqual(rng(), ("origin/HEAD", "HEAD"))
        git("branch", "-q", "up", "HEAD", cwd=self.repo)
        git("branch", "-q", "--set-upstream-to", "up", cwd=self.repo)
        self.assertEqual(rng(), ("@{upstream}", "HEAD"))

    def test_a_base_of_none_checks_every_commit_of_head(self) -> None:
        self.first_commit()
        self.write("a.txt", "a\n")
        git("add", "-A", cwd=self.repo)
        self.assertEqual(self.commit("-n").returncode, 0)
        self.assertEqual(commit_gate.check_trailers(self.repo, None, "HEAD~1"), [])
        self.assertEqual(len(commit_gate.check_trailers(self.repo, None, "HEAD")), 1)

    def test_the_trailers_option_with_no_range_reads_the_env(self) -> None:
        self.first_commit()
        env = dict(self.person, JN_CI_BASE="HEAD", JN_CI_HEAD="HEAD")
        run = subprocess.run([sys.executable, SCRIPT, "--trailers"], cwd=self.repo, env=env, capture_output=True,
                             text=True)
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        env = {k: v for k, v in self.person.items() if not k.startswith(("JN_CI_", "PRE_COMMIT_"))}
        run = subprocess.run([sys.executable, SCRIPT, "--trailers"], cwd=self.repo, env=env, capture_output=True,
                             text=True)
        self.assertEqual(run.returncode, 1)
        self.assertIn("Give the base in JN_CI_BASE", run.stderr)
        run = subprocess.run([sys.executable, SCRIPT, "--trailers", "HEAD"], cwd=self.repo, env=env,
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)

    def test_a_message_with_a_dash_line_gets_a_trailer_that_ci_reads(self) -> None:
        self.first_commit()
        self.write("a.txt", "a\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        result = git("commit", "-q", "-m", "x", "-m", "---", "-m", "below the line", cwd=self.repo,
                     env=self.person, check=False)
        self.assertGoes(result)
        self.assertEqual(self.trailers(), [])

    def test_a_commit_that_skipped_the_gate_fails_ci(self) -> None:
        self.first_commit()
        self.write("a.txt", "a\n")
        git("add", "-A", cwd=self.repo)
        self.assertEqual(self.commit("-n").returncode, 0)
        problems = self.trailers()
        self.assertEqual(len(problems), 1)
        self.assertIn("has no Commit-Gate trailer", problems[0])

    def test_a_change_after_the_gate_fails_ci(self) -> None:
        self.first_commit()
        self.change("a.txt", "a\n")
        self.write("a.txt", "changed\n")
        git("add", "-A", cwd=self.repo)
        amend = git("commit", "-q", "--amend", "--no-edit", "-n", cwd=self.repo, env=self.person, check=False)
        self.assertEqual(amend.returncode, 0, amend.stderr)
        problems = self.trailers()
        self.assertEqual(len(problems), 1)
        self.assertIn("changed after the commit gate passed it", problems[0])

    def test_a_rebase_with_no_conflict_keeps_the_trailers(self) -> None:
        self.first_commit()
        git("checkout", "-q", "-b", "side", cwd=self.repo)
        self.change("b.txt", "b\n")
        self.change("c.txt", "c\n")
        git("checkout", "-q", "main", cwd=self.repo)
        self.change("a.txt", "a\n")
        git("checkout", "-q", "side", cwd=self.repo)
        self.assertEqual(git("rebase", "-q", "main", cwd=self.repo, env=self.person, check=False).returncode, 0)
        self.assertEqual(self.trailers("main", "side"), [])

    def test_an_amend_and_an_empty_commit_through_the_gate_pass_ci(self) -> None:
        self.first_commit()
        self.change("a.txt", "a\n")
        self.write("a.txt", "a2\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.assertGoes(git("commit", "-q", "--amend", "--no-edit", cwd=self.repo, env=self.person, check=False))
        self.passed()
        self.assertGoes(self.commit("--allow-empty"))
        self.assertEqual(self.trailers("main~2", "HEAD"), [])
        self.assertEqual(git("log", "-1", "--format=%B", cwd=self.repo).stdout.count("Commit-Gate:"), 1)

    def test_a_merge_has_a_tree_trailer_that_ci_accepts(self) -> None:
        self.first_commit()
        git("checkout", "-q", "-b", "side", cwd=self.repo)
        self.change("b.txt", "b\n")
        git("checkout", "-q", "main", cwd=self.repo)
        self.change("a.txt", "a\n")
        base = git("rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        git("merge", "-q", "--no-ff", "--no-commit", "side", cwd=self.repo, env=self.person, check=False)
        self.passed()
        self.assertGoes(git("commit", "-q", "-m", "m", cwd=self.repo, env=self.person, check=False))
        self.assertIn("Commit-Gate: tree:", git("log", "-1", "--format=%B", cwd=self.repo).stdout)
        self.assertEqual(self.trailers(base + "~1", "HEAD"), [])

    def test_a_rebase_past_a_change_next_to_the_change_keeps_the_trailer(self) -> None:
        # A diff with context would hold the line that main changed, and the patch ID would change.
        self.write("a.txt", "".join(f"line {n}\n" for n in range(20)))
        self.first_commit()
        git("checkout", "-q", "-b", "side", cwd=self.repo)
        self.change("a.txt", (self.repo / "a.txt").read_text().replace("line 10\n", "ten\n"))
        git("checkout", "-q", "main", cwd=self.repo)
        self.change("a.txt", (self.repo / "a.txt").read_text().replace("line 8\n", "eight\n"))
        git("checkout", "-q", "side", cwd=self.repo)
        self.assertEqual(git("rebase", "-q", "main", cwd=self.repo, env=self.person, check=False).returncode, 0)
        self.assertEqual(self.trailers("main", "side"), [])

    def test_a_file_of_git_add_n_is_not_in_the_patch_id(self) -> None:
        self.first_commit()
        self.write("new.txt", "later\n")
        git("add", "-N", "new.txt", cwd=self.repo)
        self.write("a.txt", "a\n")
        git("add", "a.txt", cwd=self.repo)
        # The gate needs the whole worktree staged, so this commit stops; the patch ID is checked directly.
        tree = git("write-tree", cwd=self.repo).stdout.strip()
        head = git("rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        staged = commit_gate.staged_patch_id(self.repo, head)
        commit = git("commit-tree", tree, "-p", head, "-m", "x", cwd=self.repo, env=self.person).stdout.strip()
        self.assertEqual(staged, commit_gate.commit_patch_id(self.repo, commit))

    def test_an_amend_of_a_merge_passes_ci(self) -> None:
        self.first_commit()
        git("checkout", "-q", "-b", "side", cwd=self.repo)
        self.change("b.txt", "b\n")
        git("checkout", "-q", "main", cwd=self.repo)
        self.change("a.txt", "a\n")
        base = git("rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        git("merge", "-q", "--no-ff", "--no-commit", "side", cwd=self.repo, env=self.person, check=False)
        self.passed()
        self.assertGoes(git("commit", "-q", "-m", "m", cwd=self.repo, env=self.person, check=False))
        self.write("c.txt", "c\n")
        git("add", "-A", cwd=self.repo)
        self.passed()
        self.assertGoes(git("commit", "-q", "--amend", "--no-edit", cwd=self.repo, env=self.person, check=False))
        self.assertEqual(self.trailers(base + "~1", "HEAD"), [])

    def test_a_change_of_the_spaces_of_a_line_changes_the_patch_id(self) -> None:
        self.first_commit()
        head = git("rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        ids = []
        for body in ("if a:\n    b\n", "if a:\nb\n"):
            self.write("a.py", body)
            git("add", "-A", cwd=self.repo)
            ids.append(commit_gate.staged_patch_id(self.repo, head))
        self.assertNotEqual(ids[0], ids[1])



def pre_commit_python():
    """A Python that has pre-commit: the one of `pre-commit` on PATH, as uv tool install puts it there."""
    program = shutil.which("pre-commit")
    try:
        first = Path(program).read_text(errors="replace").splitlines()[0] if program else ""
    except (OSError, IndexError):
        return None
    python = first[2:].strip() if first.startswith("#!") else ""
    return python if python and os.access(python, os.X_OK) else None


@unittest.skipUnless(pre_commit_python(), "needs pre-commit on PATH")
class HookCheckTests(unittest.TestCase):
    """`commit_gate.py --check-hooks`: the check of the hook install of the tasker role."""

    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="commit-gate-hooks-")
        self.addCleanup(scratch.cleanup)
        self.base = Path(scratch.name).resolve()
        self.repo = self.base / "proj"
        self.repo.mkdir()
        git("init", "-q", cwd=self.repo)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        # A Python that has pre-commit, and one that has not.
        self.good = self.base / "good-python"
        self.good.write_text(f'#!/bin/sh\nexec "{pre_commit_python()}" "$@"\n')
        self.good.chmod(0o755)
        self.bad = self.fake("bad-python", 1)
        shutil.copy(ROOT / ".agents/skills/gcm/assets/pre-commit-config.yaml", self.repo / ".pre-commit-config.yaml")

    def fake(self, name: str, code: int) -> Path:
        path = self.base / name
        path.write_text(f"#!/bin/sh\nexit {code}\n")
        path.chmod(0o755)
        return path

    def hook(self, stage: str, python: Path, mark: str = "# File generated by pre-commit: https://pre-commit.com",
             hook_type: str = "", config: str = ".pre-commit-config.yaml") -> None:
        path = self.repo / ".git/hooks" / stage
        path.parent.mkdir(exist_ok=True)
        path.write_text(f"#!/usr/bin/env bash\n{mark}\nINSTALL_PYTHON={python}\n"
                        f"ARGS=(hook-impl --config={config} --hook-type={hook_type or stage})\n")
        path.chmod(0o755)

    def check(self, path: str = "/usr/bin:/bin") -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, SCRIPT, "--check-hooks"], cwd=self.repo, capture_output=True,
                              text=True, env=dict(os.environ, PATH=f"{self.bin}:{path}"))

    def test_the_hooks_of_the_framework_pass(self) -> None:
        for stage in commit_gate.INSTALLED_STAGES:
            self.hook(stage, self.good)
        result = self.check()
        self.assertEqual((result.returncode, result.stderr), (0, ""))

    def test_a_missing_hook_fails(self) -> None:
        for missing in commit_gate.INSTALLED_STAGES:
            with self.subTest(missing=missing):
                for stage in commit_gate.INSTALLED_STAGES:
                    self.hook(stage, self.good)
                (self.repo / ".git/hooks" / missing).unlink()
                result = self.check()
                self.assertEqual(result.returncode, 1)
                self.assertIn(f"{missing}: there is no hook", result.stderr)

    def test_a_hook_that_is_not_of_the_framework_fails(self) -> None:
        for stage in commit_gate.INSTALLED_STAGES:
            self.hook(stage, self.good)
        self.hook("pre-commit", self.good, mark="# a hook of another tool")
        self.hook("pre-merge-commit", self.good, hook_type="pre-commit")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("pre-commit: the hook is not a pre-commit hook of the pre-commit framework", result.stderr)
        self.assertIn("pre-merge-commit: the hook is not a pre-merge-commit hook", result.stderr)

    @unittest.skipUnless(shutil.which("uv"), "needs uv")
    def test_the_install_command_of_the_role_passes_the_check(self) -> None:
        text = (ROOT / "skill-package.json").read_text()
        command = json.loads("{" + next(line for line in text.splitlines() if "pre-commit install" in line)
                             .rstrip().rstrip(",") + "}")
        install = subprocess.run(command["install"].split(), cwd=self.repo, capture_output=True, text=True)
        if install.returncode != 0:
            self.skipTest(f"pre-commit cannot install here: {install.stderr.strip()}")
        result = subprocess.run([sys.executable, SCRIPT, "--check-hooks"], cwd=self.repo, capture_output=True,
                                text=True)
        self.assertEqual((result.returncode, result.stderr), (0, ""))

    def test_a_hook_of_another_config_fails(self) -> None:
        for stage in commit_gate.INSTALLED_STAGES:
            self.hook(stage, self.good)
        self.hook("pre-commit", self.good, config="other.yaml")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("pre-commit: the hook runs a config other than .pre-commit-config.yaml", result.stderr)

    def test_a_config_without_the_hooks_of_the_role_fails(self) -> None:
        # The local entry of the project took the place of the entry of the role.
        for stage in commit_gate.INSTALLED_STAGES:
            self.hook(stage, self.good)
        (self.repo / ".pre-commit-config.yaml").write_text(
            "repos:\n  - repo: local\n    hooks:\n      - id: my-own\n        name: x\n        entry: 'true'\n"
            "        language: system\n")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        for name in commit_gate.CONFIG_HOOKS:
            self.assertIn(f".pre-commit-config.yaml has no local hook {name} that runs", result.stderr)
        (self.repo / ".pre-commit-config.yaml").unlink()
        self.assertIn("there is no .pre-commit-config.yaml", self.check().stderr)

    def test_the_config_is_read_as_pre_commit_reads_it(self) -> None:
        for stage in commit_gate.INSTALLED_STAGES:
            self.hook(stage, self.good)
        config = self.repo / ".pre-commit-config.yaml"
        asset = (ROOT / ".agents/skills/gcm/assets/pre-commit-config.yaml").read_text()
        local = asset[:asset.index("  # Checks of any file")]
        gate, trailer = commit_gate.CONFIG_HOOKS["commit-gate"][1], commit_gate.CONFIG_HOOKS["commit-gate-trailer"][1]
        flow = ("repos:\n  - repo: local\n    hooks:\n"
                f"      - {{id: commit-gate, name: g, entry: \"{gate}\", language: system, "
                "stages: [pre-commit, pre-merge-commit]}\n"
                f"      - {{id: commit-gate-trailer, name: t, entry: \"{trailer}\", language: system, "
                "stages: [commit-msg]}\n"
                "      - {id: just-ci, name: c, entry: just ci, language: system, stages: [pre-push]}\n")
        cases = (
            ("the config of the role", local, 0, None),
            ("the flow form of YAML", flow, 0, None),
            ("a hook of the wrong stage", local.replace("stages: [pre-push]", "stages: [manual]"), 1, "just-ci"),
            ("a gate with no merge stage", local.replace("stages: [pre-commit, pre-merge-commit]",
                                                        "stages: [pre-commit]"), 1, "commit-gate"),
            ("a hook with another entry", local.replace("entry: just ci", "entry: 'true'"), 1, "just-ci"),
            ("the ids in a block of text", "repos:\n  - repo: local\n    hooks:\n      - id: x\n        name: x\n"
             "        entry: 'true'\n        language: system\n        args:\n          - |\n"
             "            id: commit-gate\n            id: commit-gate-trailer\n            id: just-ci\n",
             1, "commit-gate"),
            ("the ids in another repo", local.replace("repo: local", "repo: https://example.com/hooks\n    rev: v1"),
             1, "commit-gate"),
        )
        for label, text, code, missing in cases:
            with self.subTest(label):
                config.write_text(text)
                result = self.check()
                self.assertEqual(result.returncode, code, result.stderr)
                if missing:
                    self.assertIn(f"no local hook {missing} that runs", result.stderr)

    def test_the_hooks_of_the_role_match_its_config(self) -> None:
        for stage in commit_gate.INSTALLED_STAGES:
            self.hook(stage, self.good)
        self.assertEqual(commit_gate.config_problems(self.repo), [])

    def test_a_python_without_pre_commit_fails(self) -> None:
        for stage in commit_gate.INSTALLED_STAGES:
            self.hook(stage, self.good)
        self.hook("pre-commit", self.bad)
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"pre-commit: {self.bad} of the hook has no pre-commit", result.stderr)

    def test_without_its_python_the_hook_needs_pre_commit_on_path(self) -> None:
        for stage in commit_gate.INSTALLED_STAGES:
            self.hook(stage, self.base / "gone/python")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("pre-commit: pre-commit is not on PATH", result.stderr)
        program = self.bin / "pre-commit"
        program.write_text(f"#!{pre_commit_python()}\nfrom pre_commit.main import main\nmain()\n")
        program.chmod(0o755)
        self.assertEqual(self.check().returncode, 0)

    def test_the_python_of_pre_commit_on_path_is_read_from_its_first_line(self) -> None:
        for stage in commit_gate.INSTALLED_STAGES:
            self.hook(stage, self.base / "gone/python")
        program = self.bin / "pre-commit"
        # A link would lose the venv of pre-commit, so python3 on PATH is a copy of the Python that has it.
        shutil.copy(self.good, self.bin / "python3")
        cases = (
            ("a python after env", "#!/usr/bin/env python3\n", 0),
            ("the launcher of pip for a long path",
             f"#!/bin/sh\n'''exec' \"{pre_commit_python()}\" \"$0\" \"$@\"\n' '''\nfrom pre_commit.main import main\n", 0),
            ("a shell wrapper, as of pyenv", f'#!/bin/sh\nexec "{pre_commit_python()}" -m pre_commit "$@"\n', 1),
            ("a Python without pre-commit", f"#!{self.bad}\n", 1),
        )
        for label, text, code in cases:
            with self.subTest(label):
                program.write_text(text)
                program.chmod(0o755)
                result = self.check()
                self.assertEqual(result.returncode, code, result.stderr)
                if code:
                    self.assertIn("no Python with pre-commit can read .pre-commit-config.yaml", result.stderr)

    def test_a_hook_with_no_stages_runs_in_the_default_stages(self) -> None:
        for stage in commit_gate.INSTALLED_STAGES:
            self.hook(stage, self.good)
        config = self.repo / ".pre-commit-config.yaml"
        gate, trailer = commit_gate.CONFIG_HOOKS["commit-gate"][1], commit_gate.CONFIG_HOOKS["commit-gate-trailer"][1]
        hooks = ("repos:\n  - repo: local\n    hooks:\n"
                 f"      - {{id: commit-gate, name: g, entry: \"{gate}\", language: system}}\n"
                 f"      - {{id: commit-gate-trailer, name: t, entry: \"{trailer}\", language: system}}\n"
                 "      - {id: just-ci, name: c, entry: just ci, language: system}\n")
        cases = (
            ("no default_stages: each stage", hooks, 0, None),
            ("default_stages of each stage",
             "default_stages: [pre-commit, pre-merge-commit, commit-msg, pre-push]\n" + hooks, 0, None),
            ("default_stages without pre-merge-commit", "default_stages: [pre-commit, commit-msg, pre-push]\n" + hooks,
             1, "commit-gate"),
            ("default_stages without pre-commit", "default_stages: [pre-push]\n" + hooks, 1, "commit-gate"),
        )
        for label, text, code, missing in cases:
            with self.subTest(label):
                config.write_text(text)
                result = self.check()
                self.assertEqual(result.returncode, code, result.stderr)
                if missing:
                    self.assertIn(f"no local hook {missing} that runs", result.stderr)

    def test_a_module_of_the_project_cannot_answer_for_the_loader(self) -> None:
        for stage in commit_gate.INSTALLED_STAGES:
            self.hook(stage, self.good)
        asset = (ROOT / ".agents/skills/gcm/assets/pre-commit-config.yaml").read_text()
        (self.repo / ".pre-commit-config.yaml").write_text(asset.replace("entry: just ci", "entry: 'true'"))
        # A pre_commit of the project whose loader gives each hook of the role, in the folder of the check.
        hooks = [{"id": name, "entry": entry, "stages": list(stages)}
                 for name, (stages, entry) in commit_gate.CONFIG_HOOKS.items()]
        (self.repo / "pre_commit").mkdir()
        (self.repo / "pre_commit/__init__.py").write_text("")
        (self.repo / "pre_commit/clientlib.py").write_text(
            f"def load_config(path):\n    return {{'default_stages': [], 'repos': [{{'repo': 'local', "
            f"'hooks': {hooks!r}}}]}}\n")
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("no local hook just-ci that runs", result.stderr)

    def test_outside_a_repository_there_is_nothing_to_install(self) -> None:
        # An install of the hooks would fail there, at the end of each just install.
        result = subprocess.run([sys.executable, SCRIPT, "--check-hooks"], cwd=self.base, capture_output=True,
                                text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("not in a Git repository, so it has no hooks yet", result.stderr)

    def test_with_core_hooks_path_the_check_passes_and_says_what_to_do(self) -> None:
        # pre-commit refuses to install with core.hooksPath set, so the hooks of that folder must run the gate.
        git("config", "core.hooksPath", ".husky", cwd=self.repo)
        result = self.check()
        self.assertEqual(result.returncode, 0)
        self.assertIn("core.hooksPath is .husky, so pre-commit installs no hook", result.stderr)
        self.assertIn(commit_gate.GATE_COMMAND, result.stderr)

    def test_the_gate_command_is_the_entry_of_the_config(self) -> None:
        config = (ROOT / ".agents/skills/gcm/assets/pre-commit-config.yaml").read_text()
        self.assertIn(f"entry: {commit_gate.GATE_COMMAND}\n", config)
        self.assertIn(f"entry: {commit_gate.GATE_COMMAND} --hook commit-msg\n", config)

    def test_the_install_covers_each_stage(self) -> None:
        text = (ROOT / "skill-package.json").read_text()
        commands = [line for line in text.splitlines() if "pre-commit install" in line or "pre-commit uninstall" in line]
        self.assertEqual(len(commands), 2)
        for command in commands:
            for stage in commit_gate.INSTALLED_STAGES:
                self.assertIn(f"--hook-type {stage}", command)


if __name__ == "__main__":
    unittest.main()
