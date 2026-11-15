"""Check test-parent of gcm: it runs the changed test files on the parent commit and writes the case of the run."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/gcm/scripts/test_parent.py"
sys.path.insert(0, str(SCRIPT.parent))
_spec = importlib.util.spec_from_file_location("test_parent", SCRIPT)
test_parent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(test_parent)

# The recipe of the language runs each test file as a shell script, so a test file says its own exit code.
MODULE = """\
[positional-arguments]
test-paths *files:
    for f in "$@"; do sh "$f" || exit $?; done
"""


def git(*args: str, cwd: Path, env=None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


@unittest.skipUnless(shutil.which("just"), "needs just")
class TestParentTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="test-parent-test-")
        self.addCleanup(scratch.cleanup)
        self.repo = Path(scratch.name).resolve() / "proj"
        self.repo.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
                        GIT_COMMITTER_EMAIL="t@example.com")
        git("init", "-q", "-b", "main", cwd=self.repo)
        self.write("Justfile", "mod python 'py.just'\n")
        self.write("py.just", MODULE)
        self.write(".agents/stack.json", json.dumps({"tests": {"python": ["tests/**"]}}))
        self.write(".gitignore", ".agents/log/\n")

    def write(self, path: str, text: str) -> None:
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def commit(self) -> None:
        git("add", "-A", cwd=self.repo, env=self.env)
        git("commit", "-q", "-m", "x", cwd=self.repo, env=self.env)

    def run_script(self) -> tuple:
        run = subprocess.run([sys.executable, str(SCRIPT)], cwd=self.repo, capture_output=True, text=True,
                             env=self.env)
        files = list((self.repo / ".agents/log/test-parent").glob("*.json"))
        result = json.loads(files[0].read_text()) if len(files) == 1 else None
        return run, result

    def case_of(self, body: str) -> str:
        self.commit()
        self.write("tests/t.sh", body)
        run, result = self.run_script()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(result["runs"][0]["files"], ["tests/t.sh"])
        return result["runs"][0]["case"]

    def test_each_exit_code_gives_its_case(self) -> None:
        for body, case in (("exit 1\n", "failed on the parent"), ("exit 0\n", "passed on the parent"),
                           ("exit 5\n", "no test ran on the parent"), ("exit 3\n", "the runner failed")):
            with self.subTest(body=body):
                self.setUp()
                self.assertEqual(self.case_of(body), case)

    def test_the_result_is_named_by_the_worktree_tree_and_the_worktree_goes(self) -> None:
        self.commit()
        self.write("tests/t.sh", "exit 1\n")
        run, result = self.run_script()
        self.assertEqual(run.returncode, 0, run.stderr)
        tree = test_parent.worktree_diff(self.repo)[1]
        self.assertEqual(result["tree"], tree)
        self.assertTrue((self.repo / f".agents/log/test-parent/{tree}.json").is_file())
        self.assertEqual(result["parent"], git("rev-parse", "HEAD", cwd=self.repo).strip())
        self.assertEqual(len(git("worktree", "list", "--porcelain", cwd=self.repo).split("worktree ")), 2)
        self.assertIn("failed on the parent", run.stderr)

    def test_only_the_test_files_reach_the_parent(self) -> None:
        self.commit()
        # The new code is not in the parent, so the test that needs it fails there.
        self.write("src/new.sh", "true\n")
        self.write("tests/t.sh", "[ -f src/new.sh ] && exit 0 || exit 1\n")
        _, result = self.run_script()
        self.assertEqual(result["runs"][0]["case"], "failed on the parent")

    def test_each_file_runs_alone_so_a_failure_hides_no_pass(self) -> None:
        self.commit()
        self.write("tests/a.sh", "exit 1\n")
        self.write("tests/b.sh", "exit 0\n")
        run, result = self.run_script()
        self.assertEqual([(r["files"], r["case"]) for r in result["runs"]],
                         [(["tests/a.sh"], "failed on the parent"), (["tests/b.sh"], "passed on the parent")])
        self.assertIn("tests/b.sh: passed on the parent", run.stderr)

    def wait_for(self, path: Path, process: subprocess.Popen) -> None:
        for _ in range(400):
            if path.exists() or process.poll() is not None:
                break
            time.sleep(0.05)
        self.assertTrue(path.exists(), f"{path} never appeared")

    def slow_git(self, step: str, mark: Path) -> dict:
        """An env whose git touches MARK and sleeps at the worktree STEP, add after it and remove before it."""
        folder = self.repo.parent / "bin"
        folder.mkdir(exist_ok=True)
        real = shutil.which("git")
        if step == "add":
            body = f'"{real}" "$@"; code=$?\n[ "$1 $2" = "worktree add" ] && {{ touch "{mark}"; sleep 3; }}\nexit $code\n'
        else:
            body = f'[ "$1 $2" = "worktree remove" ] && {{ touch "{mark}"; sleep 2; }}\nexec "{real}" "$@"\n'
        (folder / "git").write_text("#!/bin/sh\n" + body)
        (folder / "git").chmod(0o755)
        return dict(self.env, PATH=f"{folder}:{self.env['PATH']}")

    def start(self, env=None) -> subprocess.Popen:
        return subprocess.Popen([sys.executable, str(SCRIPT)], cwd=self.repo, env=env or self.env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def worktrees(self) -> int:
        return len(git("worktree", "list", "--porcelain", cwd=self.repo).split("worktree ")) - 1

    def test_sigterm_stops_the_tests_and_removes_the_worktree(self) -> None:
        self.commit()
        mark, orphan = self.repo.parent / "started", self.repo.parent / "orphan"
        self.write("tests/t.sh", f"touch '{mark}'; sleep 2; touch '{orphan}'\n")
        process = self.start()
        self.wait_for(mark, process)
        process.terminate()
        self.assertEqual(process.wait(timeout=20), 128 + signal.SIGTERM)
        self.assertEqual(self.worktrees(), 1)
        time.sleep(3)
        self.assertFalse(orphan.exists(), "the test ran on after test-parent stopped")

    def test_sigterm_during_the_checkout_removes_the_worktree(self) -> None:
        self.commit()
        self.write("tests/t.sh", "exit 1\n")
        mark = self.repo.parent / "added"
        process = self.start(self.slow_git("add", mark))
        self.wait_for(mark, process)
        process.terminate()
        self.assertEqual(process.wait(timeout=20), 128 + signal.SIGTERM)
        self.assertEqual(self.worktrees(), 1)

    def test_a_second_sigterm_during_the_cleanup_does_not_stop_it(self) -> None:
        self.commit()
        started, removing = self.repo.parent / "started", self.repo.parent / "removing"
        self.write("tests/t.sh", f"touch '{started}'; sleep 30\n")
        process = self.start(self.slow_git("remove", removing))
        self.wait_for(started, process)
        process.terminate()
        self.wait_for(removing, process)
        process.terminate()
        self.assertEqual(process.wait(timeout=20), 128 + signal.SIGTERM)
        self.assertEqual(self.worktrees(), 1)

    def test_a_process_that_a_test_leaves_behind_neither_holds_up_nor_outlives_the_run(self) -> None:
        self.commit()
        orphan = self.repo.parent / "orphan"
        self.write("tests/t.sh", f"(sleep 3; touch '{orphan}') &\nexit 1\n")
        begin = time.monotonic()
        run, result = self.run_script()
        self.assertLess(time.monotonic() - begin, 2.5)
        self.assertEqual(result["runs"][0]["case"], "failed on the parent")
        time.sleep(3.5)
        self.assertFalse(orphan.exists(), "a process of the test ran on after the run")

    def test_a_ctrl_c_during_the_cleanup_does_not_stop_it(self) -> None:
        self.commit()
        started, removing = self.repo.parent / "started", self.repo.parent / "removing"
        self.write("tests/t.sh", f"touch '{started}'; sleep 30\n")
        env = self.slow_git("remove", removing)
        # A terminal sends Ctrl-C to each process of its foreground group, so the test makes a group of its own.
        process = subprocess.Popen([sys.executable, str(SCRIPT)], cwd=self.repo, env=env, start_new_session=True,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.wait_for(started, process)
        os.killpg(process.pid, signal.SIGINT)
        self.wait_for(removing, process)
        os.killpg(process.pid, signal.SIGINT)
        process.wait(timeout=20)
        self.assertEqual(self.worktrees(), 1)

    def test_a_burst_of_signals_still_removes_the_worktree(self) -> None:
        for number in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=number):
                self.setUp()
                self.commit()
                started = self.repo.parent / "started"
                self.write("tests/t.sh", f"touch '{started}'; sleep 30\n")
                process = subprocess.Popen([sys.executable, str(SCRIPT)], cwd=self.repo, env=self.env,
                                           start_new_session=True, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL)
                self.wait_for(started, process)
                for _ in range(4):
                    os.killpg(process.pid, number)
                    time.sleep(0.001)
                self.assertEqual(process.wait(timeout=20), 128 + number)
                self.assertEqual(self.worktrees(), 1)

    def test_a_changed_test_file_counts_and_a_deleted_one_does_not(self) -> None:
        self.write("tests/old.sh", "exit 0\n")
        self.write("tests/gone.sh", "exit 0\n")
        self.commit()
        self.write("tests/old.sh", "exit 1\n")
        (self.repo / "tests/gone.sh").unlink()
        _, result = self.run_script()
        self.assertEqual(result["runs"][0]["files"], ["tests/old.sh"])
        self.assertEqual(result["runs"][0]["case"], "failed on the parent")

    def test_no_changed_test_file_runs_nothing(self) -> None:
        self.commit()
        self.write("src/a.py", "x = 1\n")
        _, result = self.run_script()
        self.assertEqual(result["runs"], [{"language": "python", "files": [], "exit": None,
                                           "case": "no test ran on the parent",
                                           "output": "no changed file matches the test globs of the language"}])

    def test_the_first_commit_is_a_skip(self) -> None:
        self.write("tests/t.sh", "exit 1\n")
        run, result = self.run_script()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual((result["parent"], result["runs"]), (None, []))
        self.assertIn("first commit", result["skip"])

    def test_a_parent_without_the_recipe_is_a_failed_runner(self) -> None:
        self.write("py.just", "other:\n    true\n")
        self.commit()
        self.write("py.just", MODULE)
        self.write("tests/t.sh", "exit 1\n")
        _, result = self.run_script()
        self.assertEqual(result["runs"][0]["case"], "the runner failed")
        self.assertIn("no recipe python::test-paths", result["runs"][0]["output"])

    def test_a_worktree_that_git_cannot_make_fails_the_script(self) -> None:
        self.commit()
        self.write("tests/t.sh", "exit 1\n")
        git("config", "extensions.worktreeConfig", "true", cwd=self.repo)
        git("config", "core.repositoryformatversion", "0", cwd=self.repo)
        # A file in the place of the worktrees folder stops git worktree add.
        worktrees = self.repo / ".git/worktrees"
        shutil.rmtree(worktrees, ignore_errors=True)
        worktrees.write_text("not a folder\n")
        run, _ = self.run_script()
        self.assertEqual(run.returncode, 1)
        self.assertIn("git cannot make a worktree of the parent", run.stderr)

    def test_the_globs_read_as_git_reads_them(self) -> None:
        cases = (("tests/**", "tests/a/b.py", True), ("tests/**", "src/tests/a.py", False),
                 ("**/test_*.py", "test_a.py", True), ("**/test_*.py", "x/y/test_a.py", True),
                 ("**/test_*.py", "x/atest_a.py", False), ("*_test.py", "a/b_test.py", False))
        for glob, path, match in cases:
            with self.subTest(glob=glob, path=path):
                self.assertEqual(bool(test_parent.glob_pattern(glob).match(path)), match)


if __name__ == "__main__":
    unittest.main()
