"""Check the pre-push hook of gcm, pre_push.py, in scratch repositories with a Justfile whose recipes log their runs."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/gcm/scripts/pre_push.py"

# Each recipe adds its name to the file in RAN, outside the repository, so the worktree keeps the tree of the commit.
JUSTFILE = """\
check: lint typecheck
    echo check >> "$RAN"
lint:
    echo lint >> "$RAN"
vendor:
    echo vendor >> "$RAN"
typecheck: vendor
    echo typecheck >> "$RAN"
extra:
    echo extra >> "$RAN"
fails:
    exit 3
with-arg word:
    echo with-arg >> "$RAN"
ci-gate:
    echo ci-gate >> "$RAN"
"""

STACK = {"steps": ["lint", "typecheck"]}


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@unittest.skipUnless(shutil.which("just"), "needs just")
class PrePushTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="pre-push-test-")
        self.addCleanup(scratch.cleanup)
        self.base = Path(scratch.name).resolve()
        self.repo = self.base / "proj"
        self.repo.mkdir()
        self.ran = self.base / "ran.txt"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "PRE_COMMIT"))}
        self.env.update(RAN=str(self.ran), GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
        git("init", "-q", "-b", "main", cwd=self.repo)
        (self.repo / ".agents").mkdir()
        (self.repo / ".agents/stack.json").write_text(json.dumps(STACK))
        (self.repo / ".gitignore").write_text(".agents/log/\n")

    def commit(self, ci: str) -> str:
        """Commit the Justfile with the recipe CI, and give the tree of the commit."""
        (self.repo / "Justfile").write_text(JUSTFILE + ci)
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, env=self.env)
        subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=self.repo, check=True, env=self.env)
        return git("rev-parse", "HEAD^{tree}", cwd=self.repo).strip()

    def passed(self, tree: str, steps=("lint", "typecheck"), argv=("just", "check"), run="run-1") -> None:
        """The lines of the run log that `just check` writes for a pass of TREE."""
        log = self.repo / ".agents/log"
        log.mkdir(parents=True, exist_ok=True)
        lines = [{"kind": "line", "run": run, "argv": list(argv), "line": "jlog pass", "exit": 0},
                 {"kind": "pass", "run": run, "tree": tree, "steps": list(steps)}]
        with (log / "just.jsonl").open("a") as out:
            out.writelines(json.dumps(line) + "\n" for line in lines)

    def push(self, **env: str) -> subprocess.CompletedProcess:
        head = git("rev-parse", "HEAD", cwd=self.repo).strip()
        full = dict(self.env, PRE_COMMIT_FROM_REF=head, PRE_COMMIT_TO_REF=head)
        full.update(env)
        full = {k: v for k, v in full.items() if v}
        return subprocess.run([sys.executable, str(SCRIPT)], cwd=self.repo, env=full, capture_output=True, text=True)

    def runs(self) -> list:
        return self.ran.read_text().split() if self.ran.exists() else []

    def test_a_pushed_tree_with_a_pass_runs_only_ci_gate(self) -> None:
        self.passed(self.commit("ci: vendor lint ci-gate\n"))
        result = self.push()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.runs(), ["ci-gate"])
        self.assertIn("ran vendor, lint, so the hook runs only ci-gate", result.stderr)
        self.assertEqual(len([line for line in result.stderr.splitlines() if line.startswith("pre-push:")]), 1)

    def test_a_pushed_tree_with_no_pass_runs_all_of_just_ci(self) -> None:
        self.commit("ci: vendor lint ci-gate\n")
        result = self.push()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.runs(), ["vendor", "lint", "ci-gate"])
        self.assertIn("runs all of just ci, since the run log holds no pass", result.stderr)

    def test_a_ci_step_outside_check_still_runs(self) -> None:
        self.passed(self.commit("ci: lint extra ci-gate\n"))
        result = self.push()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.runs(), ["extra", "ci-gate"])

    def test_a_failing_recipe_that_runs_stops_the_push(self) -> None:
        self.passed(self.commit("ci: lint fails ci-gate\n"))
        result = self.push()
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(self.runs(), [])

    def test_a_pass_of_another_tree_runs_all_of_just_ci(self) -> None:
        tree = self.commit("ci: lint ci-gate\n")
        self.passed(tree)
        self.commit("ci: vendor lint ci-gate\n")
        result = self.push()
        self.assertEqual(self.runs(), ["vendor", "lint", "ci-gate"])
        self.assertIn("no pass", result.stderr)

    def test_a_pass_that_lacks_a_step_runs_all_of_just_ci(self) -> None:
        self.passed(self.commit("ci: lint ci-gate\n"), steps=("lint",))
        self.push()
        self.assertEqual(self.runs(), ["lint", "ci-gate"])

    def test_a_pass_that_did_not_come_from_just_check_runs_all_of_just_ci(self) -> None:
        for argv in (("just", "verify"), ("just", "--justfile", "other.just", "check"), ("sh",)):
            with self.subTest(argv=argv):
                self.setUp()
                self.passed(self.commit("ci: lint ci-gate\n"), argv=argv)
                self.push()
                self.assertEqual(self.runs(), ["lint", "ci-gate"])

    def test_a_pass_and_a_check_line_of_two_runs_do_not_count(self) -> None:
        tree = self.commit("ci: lint ci-gate\n")
        self.passed(tree, argv=("just", "verify"), run="run-1")
        self.passed("0" * 40, run="run-2")
        self.push()
        self.assertEqual(self.runs(), ["lint", "ci-gate"])

    def test_a_worktree_that_is_not_the_pushed_tree_runs_all_of_just_ci(self) -> None:
        self.passed(self.commit("ci: lint ci-gate\n"))
        (self.repo / "new.txt").write_text("x\n")
        result = self.push()
        self.assertEqual(self.runs(), ["lint", "ci-gate"])
        self.assertIn("the worktree is not the tree of the pushed commit", result.stderr)

    def test_a_push_with_no_pushed_commit_runs_all_of_just_ci(self) -> None:
        self.passed(self.commit("ci: lint ci-gate\n"))
        self.push(PRE_COMMIT_TO_REF="", PRE_COMMIT_FROM_REF="", PRE_COMMIT_LOCAL_BRANCH="refs/heads/main")
        self.assertEqual(self.runs(), ["lint", "ci-gate"])

    def test_a_ci_with_lines_of_its_own_runs_all_of_just_ci(self) -> None:
        self.passed(self.commit('ci: lint ci-gate\n    echo ci >> "$RAN"\n'))
        self.push()
        self.assertEqual(self.runs(), ["lint", "ci-gate", "ci"])

    def test_a_dependency_with_arguments_runs_all_of_just_ci(self) -> None:
        self.passed(self.commit('ci: lint (with-arg "a") ci-gate\n'))
        self.push()
        self.assertEqual(self.runs(), ["lint", "with-arg", "ci-gate"])

    def test_a_dependency_that_check_runs_with_arguments_is_not_done(self) -> None:
        justfile = 'other: (with-arg "a")\n    echo other >> "$RAN"\nci: lint other ci-gate\n'
        text = JUSTFILE.replace("check: lint typecheck", 'check: lint typecheck (with-arg "a")')
        (self.repo / "Justfile").write_text(text + justfile)
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, env=self.env)
        subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=self.repo, check=True, env=self.env)
        self.passed(git("rev-parse", "HEAD^{tree}", cwd=self.repo).strip())
        self.push()
        self.assertEqual(self.runs(), ["with-arg", "other", "ci-gate"])

    def test_ci_gate_runs_though_check_runs_it(self) -> None:
        text = JUSTFILE.replace("check: lint typecheck", "check: lint typecheck ci-gate")
        (self.repo / "Justfile").write_text(text + "ci: lint ci-gate\n")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, env=self.env)
        subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=self.repo, check=True, env=self.env)
        self.passed(git("rev-parse", "HEAD^{tree}", cwd=self.repo).strip())
        self.push()
        self.assertEqual(self.runs(), ["ci-gate"])

    def set_justfile(self, text: str) -> None:
        (self.repo / "Justfile").write_text(text)
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, env=self.env)
        subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=self.repo, check=True, env=self.env)
        self.passed(git("rev-parse", "HEAD^{tree}", cwd=self.repo).strip())

    def test_a_dependency_of_check_after_its_lines_is_not_done(self) -> None:
        # jlog pass runs before a dependency after &&, so the pass does not show that it passed.
        text = JUSTFILE.replace("check: lint typecheck", "check: lint typecheck && extra")
        self.set_justfile(text + "ci: lint extra ci-gate\n")
        self.push()
        self.assertEqual(self.runs(), ["extra", "ci-gate"])

    def test_a_dependency_after_the_lines_of_another_recipe_is_done(self) -> None:
        text = JUSTFILE.replace("typecheck: vendor", "typecheck: vendor && extra")
        self.set_justfile(text + "ci: lint extra ci-gate\n")
        self.push()
        self.assertEqual(self.runs(), ["ci-gate"])

    def test_a_recipe_of_a_module_runs_all_of_just_ci(self) -> None:
        # The JSON dump names sub::lint as lint, like the lint of the Justfile that check runs.
        (self.repo / "sub.just").write_text('lint:\n    echo sub-lint >> "$RAN"\n')
        self.set_justfile("mod sub\n" + JUSTFILE + "ci: sub::lint ci-gate\n")
        result = self.push()
        self.assertEqual(self.runs(), ["sub-lint", "ci-gate"])
        self.assertIn("names a recipe of a module", result.stderr)

    def test_a_module_that_ci_and_check_do_not_name_keeps_the_proof(self) -> None:
        (self.repo / "sub.just").write_text('lint:\n    echo sub-lint >> "$RAN"\n')
        self.set_justfile("mod sub\n" + JUSTFILE + "other: sub::lint\nci: lint ci-gate\n")
        self.push()
        self.assertEqual(self.runs(), ["ci-gate"])

    def test_a_done_dependency_that_runs_ci_gate_still_runs(self) -> None:
        # The ci-gate of the pass came before the last commit, so the trailers of the push need a run of their own.
        text = JUSTFILE.replace("check: lint typecheck", "check: lint typecheck static")
        self.set_justfile(text + 'static: lint ci-gate\n    echo static >> "$RAN"\nci: lint static\n')
        self.push()
        self.assertEqual(self.runs(), ["lint", "ci-gate", "static"])

    def test_a_recipe_of_a_module_in_an_imported_file_runs_all_of_just_ci(self) -> None:
        (self.repo / "sub.just").write_text('lint:\n    echo sub-lint >> "$RAN"\n')
        (self.repo / "extra.just").write_text("fast: sub::lint\n")
        text = JUSTFILE.replace("check: lint typecheck", "check: fast typecheck")
        self.set_justfile("mod sub\nimport 'extra.just'\n" + text + "ci: lint ci-gate\n")
        result = self.push()
        self.assertEqual(self.runs(), ["lint", "ci-gate"])
        self.assertIn("names a recipe of a module", result.stderr)

    def test_an_import_line_that_the_script_cannot_read_runs_all_of_just_ci(self) -> None:
        for line in ("import? '''x.just'''", "import? x'x.just'", "import x'x.just'", "import? '~/x.just'",
                     'import? "x\\u{2e}just"'):
            with self.subTest(line=line):
                self.setUp()
                (self.repo / "x.just").write_text("fast: lint\n")
                self.set_justfile(line + "\n" + JUSTFILE + "ci: lint ci-gate\n")
                result = self.push()
                self.assertEqual(self.runs(), ["lint", "ci-gate"])
                self.assertIn("cannot read the import line", result.stderr)

    def test_an_import_that_is_missing_keeps_the_proof(self) -> None:
        self.set_justfile("import? 'gone.just'\n" + JUSTFILE + "ci: lint ci-gate\n")
        self.push()
        self.assertEqual(self.runs(), ["ci-gate"])

    def test_a_default_with_an_equals_sign_does_not_hide_a_module(self) -> None:
        (self.repo / "sub.just").write_text('lint:\n    echo sub-lint >> "$RAN"\n')
        text = JUSTFILE.replace("check: lint typecheck", 'check p=":=": sub::lint typecheck')
        self.set_justfile("mod sub\n" + text + "ci: lint ci-gate\n")
        self.push()
        self.assertEqual(self.runs(), ["lint", "ci-gate"])

    def test_a_done_dependency_that_names_ci_gate_in_a_line_still_runs(self) -> None:
        text = JUSTFILE.replace("check: lint typecheck", "check: lint typecheck static")
        self.set_justfile(text + 'static: lint\n    just ci-gate\nci: lint static\n')
        self.push()
        self.assertEqual(self.runs(), ["lint", "ci-gate"])

    def test_a_done_dependency_that_runs_ci_gate_with_arguments_still_runs(self) -> None:
        text = JUSTFILE.replace("ci-gate:\n", "ci-gate *a:\n").replace("check: lint typecheck",
                                                                       "check: lint typecheck static")
        self.set_justfile(text + 'static: lint (ci-gate "x")\nci: lint static\n')
        self.push()
        self.assertEqual(self.runs(), ["lint", "ci-gate"])

    def test_the_hook_passes_the_push_range_to_the_recipes(self) -> None:
        justfile = 'ci-gate:\n    echo "$PRE_COMMIT_FROM_REF" >> "$RAN"\n'
        text = JUSTFILE[:JUSTFILE.index("ci-gate:")] + justfile
        (self.repo / "Justfile").write_text(text + "ci: lint ci-gate\n")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, env=self.env)
        subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=self.repo, check=True, env=self.env)
        self.passed(git("rev-parse", "HEAD^{tree}", cwd=self.repo).strip())
        self.push(PRE_COMMIT_FROM_REF="abc")
        self.assertEqual(self.runs(), ["abc"])


if __name__ == "__main__":
    unittest.main()
