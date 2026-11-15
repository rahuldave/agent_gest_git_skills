"""Tests of stack_prs.py, with a bare origin and a fake gh that keeps its PRs in a JSON file."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/gcm/scripts/stack_prs.py"

# A gh with `pr list --head H ...` and `pr create --base B --head H --fill`. The PRs are in $FAKE_GH_STATE.
FAKE_GH = '''#!/usr/bin/env python3
import json, os, sys
state = os.environ["FAKE_GH_STATE"]
prs = json.load(open(state)) if os.path.exists(state) else []
args = sys.argv[1:]
value = lambda name: args[args.index(name) + 1]
if args[:2] == ["pr", "list"]:
    print(json.dumps([p for p in prs if p["headRefName"] == value("--head")]))
elif args[:2] == ["pr", "create"]:
    number = len(prs) + 1
    prs.append({"number": number, "headRefName": value("--head"), "baseRefName": value("--base"),
                "url": f"https://example.com/pull/{number}"})
    json.dump(prs, open(state, "w"))
    print(prs[-1]["url"])
else:
    sys.exit(f"fake gh: {args}")
'''


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


class StackPrsTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="stack-prs-")
        self.addCleanup(scratch.cleanup)
        base = Path(scratch.name).resolve()
        self.origin, self.repo, self.bin = base / "origin.git", base / "repo", base / "bin"
        git("init", "-q", "--bare", str(self.origin), cwd=base)
        self.repo.mkdir()
        self.bin.mkdir()
        git("init", "-q", "-b", "main", cwd=self.repo)
        for key, value in (("user.name", "t"), ("user.email", "t@example.com"), ("commit.gpgsign", "false")):
            git("config", key, value, cwd=self.repo)
        git("remote", "add", "origin", str(self.origin), cwd=self.repo)
        self.commit("base")
        git("push", "-q", "-u", "origin", "main", cwd=self.repo)
        for branch, below in (("one", "main"), ("two", "one")):
            git("switch", "-q", "-c", branch, below, cwd=self.repo)
            self.commit(branch)
        gh = self.bin / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        self.state = base / "prs.json"

    def commit(self, name: str) -> None:
        (self.repo / f"{name}.txt").write_text(name)
        git("add", ".", cwd=self.repo)
        git("commit", "-q", "-m", name, cwd=self.repo)

    def stack(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", FAKE_GH_STATE=str(self.state))
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.repo, env=env, capture_output=True,
                              text=True)

    def prs(self) -> list:
        return json.loads(self.state.read_text()) if self.state.exists() else []

    def remote_branches(self) -> str:
        return git("branch", "--list", cwd=self.origin)

    def test_the_prs_open_from_the_bottom_up_on_the_branch_below(self) -> None:
        result = self.stack("main", "one", "two")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([(p["headRefName"], p["baseRefName"]) for p in self.prs()], [("one", "main"), ("two", "one")])
        self.assertIn("one", self.remote_branches())
        self.assertIn("two", self.remote_branches())
        # A second run opens no PR and pushes nothing.
        again = self.stack("main", "one", "two")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(len(self.prs()), 2)
        self.assertIn("two has its PR on one", again.stdout)

    def test_a_dry_run_changes_nothing(self) -> None:
        result = self.stack("--dry-run", "main", "one", "two")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would open the PR of two on one", result.stdout)
        self.assertEqual(self.prs(), [])
        self.assertNotIn("one", self.remote_branches())

    def test_branches_out_of_order_stop_before_any_change(self) -> None:
        result = self.stack("main", "two", "one")
        self.assertEqual(result.returncode, 1)
        self.assertIn("one does not contain two", result.stderr)
        self.assertEqual(self.prs(), [])
        self.assertEqual(self.remote_branches().split(), ["main"])

    def test_a_pr_with_another_base_stops(self) -> None:
        self.state.write_text(json.dumps([{"number": 7, "headRefName": "two", "baseRefName": "main",
                                           "url": "https://example.com/pull/7"}]))
        result = self.stack("main", "one", "two")
        self.assertEqual(result.returncode, 1)
        self.assertIn("has the base main and not one", result.stderr)
        self.assertIn("gh pr edit 7 --base one", result.stderr)
        # It stops before it pushes or opens anything for the branches below.
        self.assertEqual(len(self.prs()), 1)
        self.assertEqual(self.remote_branches().split(), ["main"])

    def test_a_repeated_branch_or_the_base_in_the_stack_stops(self) -> None:
        for args in (("main", "one", "one"), ("main", "main", "one")):
            with self.subTest(args=args):
                result = self.stack(*args)
                self.assertEqual(result.returncode, 1)
                self.assertIn("must appear once, and not be the base", result.stderr)
                self.assertEqual(self.prs(), [])

    def test_a_branch_ahead_of_its_upstream_is_pushed(self) -> None:
        self.assertEqual(self.stack("main", "one", "two").returncode, 0)
        git("switch", "-q", "two", cwd=self.repo)
        self.commit("more")
        result = self.stack("main", "one", "two")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pushes two to origin", result.stdout)
        self.assertEqual(git("rev-parse", "two", cwd=self.repo), git("rev-parse", "two", cwd=self.origin))

    def test_a_branch_behind_its_upstream_or_with_another_upstream_stops(self) -> None:
        self.assertEqual(self.stack("main", "one", "two").returncode, 0)
        git("reset", "-q", "--hard", "one", cwd=self.repo)
        self.commit("other")
        result = self.stack("main", "one", "two")
        self.assertEqual(result.returncode, 1)
        self.assertIn("origin/two has commits that two does not", result.stderr)
        git("switch", "-q", "-c", "three", "origin/main", cwd=self.repo)
        self.commit("three")
        result = self.stack("main", "three")
        self.assertEqual(result.returncode, 1)
        self.assertIn("the upstream of three is origin/main, not origin/three", result.stderr)

    def test_too_few_arguments_print_the_usage(self) -> None:
        result = self.stack("main")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage: stack_prs.py", result.stderr)


if __name__ == "__main__":
    unittest.main()
