"""Verify hook decisions in real plain Git and GitButler workspace checkouts."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = {
    "claude": ROOT / ".claude/hooks/raw-git-write-guard.sh",
    "codex": ROOT / ".codex/hooks/raw-git-write-guard.sh",
}


class RawGitGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="gest-hook-test-")
        self.addCleanup(scratch.cleanup)
        self.repo = Path(scratch.name) / "repo"
        subprocess.run(["git", "init", "-b", "main", str(self.repo)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "hook-test"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "hook-test@example.invalid"], check=True)
        (self.repo / "README.md").write_text("scratch\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "init"], check=True)

    def decision(self, adapter: str, command: str, mode: str | None = None) -> bool:
        payload = {"command": command} if adapter == "claude" else {"tool_input": {"cmd": command}}
        env = os.environ.copy()
        env.pop("GEST_VCS_EXECUTION", None)
        if mode is not None:
            env["GEST_VCS_EXECUTION"] = mode
        completed = subprocess.run(
            ["bash", str(HOOKS[adapter])],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=self.repo,
            env=env,
            check=True,
        )
        return "permissionDecision" in completed.stdout

    def test_plain_git_checkout_allows_raw_writes(self) -> None:
        for adapter in HOOKS:
            with self.subTest(adapter=adapter):
                self.assertFalse(self.decision(adapter, "git commit -m ordinary"))
                self.assertFalse(self.decision(adapter, "git -C . push origin main"))
                self.assertFalse(self.decision(adapter, "but commit demo -m okay"))

    def test_managed_workspace_blocks_raw_writes_but_allows_reads_and_but(self) -> None:
        subprocess.run(["git", "-C", str(self.repo), "switch", "-qc", "gitbutler/workspace"], check=True)
        for adapter in HOOKS:
            with self.subTest(adapter=adapter):
                self.assertTrue(self.decision(adapter, "git commit -m blocked"))
                self.assertTrue(self.decision(adapter, "git -C . push origin demo"))
                self.assertFalse(self.decision(adapter, "git diff --stat"))
                self.assertFalse(self.decision(adapter, "but commit demo -m okay"))
                self.assertFalse(self.decision(adapter, "GEST_VCS_EXECUTION=git-worktrees git worktree add /tmp/demo main"))
                self.assertFalse(self.decision(adapter, "git worktree add /tmp/demo main", "git-worktrees"))
                self.assertTrue(self.decision(adapter, "echo GEST_VCS_EXECUTION=git-worktrees; git commit -m blocked"))

    def test_explicit_managed_mode_blocks_raw_writes_on_plain_branch(self) -> None:
        for adapter in HOOKS:
            with self.subTest(adapter=adapter):
                self.assertTrue(self.decision(adapter, "git add README.md", "gitbutler-workspace"))
                self.assertTrue(self.decision(adapter, "GEST_VCS_EXECUTION=gitbutler-workspace git add README.md"))


if __name__ == "__main__":
    unittest.main()
