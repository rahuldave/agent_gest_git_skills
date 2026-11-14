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
        self.person = {k: v for k, v in os.environ.items()
                       if k not in commit_gate.AGENT_VARIABLES and not k.startswith("GIT_")}
        self.person.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
                           GIT_COMMITTER_EMAIL="t@example.com")
        self.agent = dict(self.person, CLAUDE_CODE_SESSION_ID="session-1")
        git("init", "-q", "-b", "main", cwd=self.repo)
        for hook in ("pre-commit", "pre-merge-commit"):
            path = self.repo / ".git/hooks" / hook
            path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{SCRIPT}" --hook {hook}\n')
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
        for hook in ("pre-commit", "pre-merge-commit"):
            (self.repo / ".git/hooks" / hook).rename(self.base / hook)
        git("add", "-A", cwd=self.repo)
        self.assertGoes(self.commit())
        (self.base / "stack.json").rename(stack)
        for hook in ("pre-commit", "pre-merge-commit"):
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


if __name__ == "__main__":
    unittest.main()
