"""Verify that the installed Bash hooks never block plain git, in both tasker variants."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = (
    "git commit -m ordinary",
    "git -C . commit -m ordinary",
    "git switch -c feature",
    "git checkout main",
    "git -C . push origin main",
    "git rebase --update-refs main",
    "git worktree add ../demo main",
)


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class InstalledHookTests(unittest.TestCase):
    """Copy the hooks and their settings into a scratch project, as the installer does, and run them."""

    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="gest-hook-test-")
        self.addCleanup(scratch.cleanup)
        self.repo = Path(scratch.name).resolve() / "repo"
        self.repo.mkdir()
        git("init", "-qb", "main", cwd=self.repo)
        git("config", "user.name", "hook-test", cwd=self.repo)
        git("config", "user.email", "hook-test@example.invalid", cwd=self.repo)
        for folder, settings in ((".claude", "settings.json"), (".codex", "hooks.json")):
            shutil.copytree(ROOT / folder / "hooks", self.repo / folder / "hooks")
            shutil.copy(ROOT / folder / settings, self.repo / folder / settings)
        (self.repo / "README.md").write_text("scratch\n")
        git("add", "README.md", cwd=self.repo)
        git("commit", "-qm", "init", cwd=self.repo)

    def variant(self, name: str) -> None:
        (self.repo / ".agents").mkdir(exist_ok=True)
        (self.repo / ".agents/stack.json").write_text(json.dumps(
            {"version": 2, "choices": {"tasker": True}, "variants": {"tasker": name}}, indent=2) + "\n")

    def bash_hooks(self) -> list[tuple[str, str]]:
        """Each PreToolUse command that the settings register for Bash, with its adapter."""
        hooks = []
        for adapter, settings in (("claude", ".claude/settings.json"), ("codex", ".codex/hooks.json")):
            for entry in json.loads((self.repo / settings).read_text())["hooks"].get("PreToolUse", []):
                if entry.get("matcher") != "Bash":
                    continue
                for hook in entry["hooks"]:
                    hooks.append((adapter, hook["command"]))
        self.assertGreaterEqual(len(hooks), 2)
        return hooks

    def outputs(self, command: str) -> list[str]:
        env = {key: value for key, value in os.environ.items() if not key.startswith("GEST_")}
        env["CLAUDE_PROJECT_DIR"] = str(self.repo)
        results = []
        for adapter, hook in self.bash_hooks():
            payload = {"tool_input": {"command": command}} if adapter == "claude" else {"tool_input": {"cmd": command}}
            done = subprocess.run(["sh", "-c", hook], input=json.dumps(payload), text=True, capture_output=True,
                                  cwd=self.repo, env=env)
            self.assertEqual(done.returncode, 0, f"{hook}: {done.stderr}")
            results.append(done.stdout)
        return results

    def assert_not_blocked(self, command: str) -> None:
        for out in self.outputs(command):
            self.assertNotIn("permissionDecision", out, command)
            self.assertNotIn('"decision"', out, command)
            self.assertNotIn('"continue":false', out.replace(" ", ""), command)

    def test_plain_git_is_never_blocked(self) -> None:
        for variant in (None, "git", "gitwt"):
            if variant:
                self.variant(variant)
            for command in COMMANDS:
                with self.subTest(variant=variant, command=command):
                    self.assert_not_blocked(command)

    def test_a_branch_named_like_the_old_workspace_changes_nothing(self) -> None:
        git("switch", "-qc", "git" "butler/workspace", cwd=self.repo)
        for command in COMMANDS:
            with self.subTest(command=command):
                self.assert_not_blocked(command)
                for out in self.outputs(command):
                    self.assertEqual(out, "")

    def test_plain_git_commit_switch_and_checkout_run_after_the_hooks(self) -> None:
        for command in ("git commit -m ordinary", "git switch -c feature", "git checkout main"):
            self.assert_not_blocked(command)
        (self.repo / "README.md").write_text("changed\n")
        git("add", "README.md", cwd=self.repo)
        git("commit", "-qm", "ordinary", cwd=self.repo)
        git("switch", "-qc", "feature", cwd=self.repo)
        git("checkout", "-q", "main", cwd=self.repo)

    def test_the_commit_context_is_valid_json_with_a_tab_in_the_rules(self) -> None:
        (self.repo / "docs/dev").mkdir(parents=True)
        (self.repo / "docs/dev/commits.md").write_text("# Commits\n\n\tUse \"feat:\" and a \\ path.\n")
        for command in ("git commit -m x", "git push origin main", "gh pr create --base main"):
            with self.subTest(command=command):
                outs = [out for out in self.outputs(command) if out]
                self.assertEqual(len(outs), 1)
                payload = json.loads(outs[0])["hookSpecificOutput"]
                self.assertEqual(payload["hookEventName"], "PreToolUse")
                self.assertIn("feat:", payload["additionalContext"])

    def test_no_hook_or_setting_names_a_marker_or_the_old_tool(self) -> None:
        for path in sorted((self.repo / ".claude").rglob("*")) + sorted((self.repo / ".codex").rglob("*")):
            if path.is_file():
                text = path.read_text().lower()
                with self.subTest(path=path.name):
                    self.assertNotIn("git" "butler", text)
                    self.assertNotIn("gest_vcs_execution", text)


if __name__ == "__main__":
    unittest.main()
