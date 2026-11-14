"""Check the gate guard of gcm: the commands that it stops, the ones that it lets run, and the installed hooks."""

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
SCRIPT = ROOT / ".agents/skills/gcm/scripts/gate_guard.py"

STOPPED = (
    "git commit --no-verify -m x",
    "git commit -n -m x",
    "git commit -anm x",
    "git commit -m x --no-veri",
    "git -C . commit --no-verify",
    "git -c user.name=x commit -n",
    "cd sub && git commit --no-verify -m x",
    "true; git commit -n",
    "echo $(git commit --no-verify)",
    "env A=1 git commit --no-verify",
    "/usr/bin/git commit -n",
    "git merge --no-verify side",
    "git pull --no-verify",
    "git -c core.hooksPath=/dev/null commit -m x",
    "git config core.hooksPath .hooks",
    "GIT_CONFIG_VALUE_0=core.hooksPath git commit -m x",
    "git commit-tree HEAD^{tree} -m x",
    "git update-ref refs/heads/main HEAD",
    "echo '{}' > .agents/log/records/r.json",
    "cat x >> .agents/log/just.jsonl",
    "cp r.json .agents/log/records/",
    "rm -rf .agents/log",
    "tee .git/hooks/pre-commit < x",
    "sed -i '' s/a/b/ .agents/targets/required.txt",
    "mv x .pre-commit-config.yaml",
    "echo x > .claude/settings.json",
    "echo x > ./sub/../.codex/hooks.json",
    "echo hi\ngit commit -n",
    "cd sub\ngit commit --no-verify -m x",
    "sh -c 'git commit --no-verify -m x'",
    "bash -lc \"git commit -n\"",
    "eval 'git commit --no-verify'",
    "echo x | xargs git commit -n",
    "sudo -u me git commit -n",
    "nice -n 5 git commit -n",
    "timeout 10 git commit -n",
    "git commit -m `date` -n",
    "git commit -m \"$(date)\" --no-verify",
    "git -c alias.c=commit c -n",
    "git -ccore.hooksPath=x commit",
    "git config --file .git/config core.hooksPath h",
    "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath; git commit",
    "git rebase --exec 'git commit --amend -n' main",
    "sed --in-place s/a/b/ .agents/targets/required.txt",
    "perl -pi -e s/a/b/ .pre-commit-config.yaml",
    "dd if=x of=.git/hooks/pre-commit",
    "echo x > .agents//log/x",
    "echo x > .agents/./log/x",
    "mv .claude/settings.json old.json",
    "echo x 2> .agents/log/x",
    "if true; then git commit -n; fi",
    "for f in a b; do git commit --no-verify -m $f; done",
    "for f in a; do cp $f .agents/log/; done",
    "! git commit -n",
    "while true; do git commit -n; break; done",
    "# don't skip this\ngit commit -n",
    "echo it\\'s\ngit commit -n",
    "git config set core.hooksPath /dev/null",
    "bash <<'EOF'\ngit commit --no-verify -m x\nEOF",
    "grep x <<< 'hello'\ngit commit -n",
    "echo $((1 << 2))\ngit commit -n",
    "echo $((x << y))\ngit commit -n",
    "cat > n.md <<'EOF'\nx\nEOF\ngit commit -n",
    "git commit -m \"doc: use <<EOF in bash\"\ngit commit -n",
    "cp hook \"$(git rev-parse --git-dir)/hooks/pre-commit\"",
    "cp hook \"$(git rev-parse --show-toplevel)/.git/hooks/pre-commit\"",
    "echo x > \"$PWD/.agents/log/x\"",
    "cp hook \"$(git rev-parse --git-path hooks)/pre-commit\"",
    "H=$(git rev-parse --git-path hooks); cp hook $H/pre-commit",
    "(cd sub && ls); echo x > .agents/log/x",
    "cd /tmp; cd -; echo x > .agents/log/x",
    "GIT_CONFIG_KEY_0=core.hooksPath; git commit -m x",
    "mkdir -p sub && cd sub && cp hook \"$(git rev-parse --git-dir)/hooks/pre-commit\"",
    "mkdir -p sub && cd sub && cp hook \"$(git rev-parse --git-path hooks)/pre-commit\"",
    "mkdir -p sub && cd sub && echo x > ../.agents/log/x",
)

ALLOWED = (
    "git commit -m 'fix the --no-verify docs'",
    "git commit -m x -- --no-verify",
    "git commit -m nothing",
    "git commit -am x",
    "git commit -c HEAD",
    "git merge -n side",
    "git push --no-verify origin main",
    "git log --no-walk",
    "git rebase --update-refs main",
    "grep -n hooksPath docs/specs/commit-gates.md",
    "cat .agents/log/just.jsonl",
    "ls .git/hooks",
    "just check",
    "just install",
    "echo 'git commit -n' > notes.txt",
    "git commit -m 'unclosed",
    "git commit -F - <<'EOF'\nfix: handle the -n flag\nEOF",
    "git commit -m 'docs: explain core.hooksPath'",
    "git log --grep=hooksPath",
    "git grep hooksPath",
    "git config core.hooksPath",
    "git config --unset core.hooksPath",
    "cp .claude/settings.json backup.json",
    "cp .pre-commit-config.yaml /tmp/backup",
    "sh -c 'git commit -m x'",
    "git commit -Sn -m x",
    "git commit -m 'line one\nline two -n'",
    "cat .agents/log.txt > .agents/logs",
    "cat > n.md <<'EOF'\ngit commit -n\nEOF",
    "cp hook /tmp/test-repo/.git/hooks/pre-commit",
    "mkdir -p /tmp/x/.git/hooks",
    "perl -Mstrict -ne print .agents/log/just.jsonl",
    "sed -n p .agents/targets/required.txt",
    "git config get core.hooksPath",
    "echo '# not a comment' && git commit -m x",
    "if git diff --quiet; then echo clean; fi",
    "cp x \"$scratch/repo/.git/hooks/pre-commit\"",
    "mkdir -p \"$TMPDIR/hooks\" && cp x \"$TMPDIR/hooks/\"",
    "cd \"$unknown\" && echo x > .agents/log/x",
)


def guard(payload: dict, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(payload), text=True, capture_output=True,
                          cwd=cwd)


class GuardTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="gate-guard-test-")
        self.addCleanup(scratch.cleanup)
        self.repo = Path(scratch.name).resolve() / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.repo, check=True)

    def run_command(self, command, key: str = "command") -> subprocess.CompletedProcess:
        return guard({"tool_name": "Bash", "tool_input": {key: command}, "cwd": str(self.repo)}, self.repo)

    def test_each_command_that_goes_around_the_gate_stops(self) -> None:
        for command in STOPPED:
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual(result.returncode, 2, command)
                self.assertIn("gate guard:", result.stderr)

    def test_each_ordinary_command_runs(self) -> None:
        for command in ALLOWED:
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)

    def test_an_alias_of_commit_is_checked(self) -> None:
        subprocess.run(["git", "config", "alias.ci", "commit"], cwd=self.repo, check=True)
        self.assertEqual(self.run_command("git ci -n -m x").returncode, 2)
        self.assertEqual(self.run_command("git ci -m x").returncode, 0)

    def test_a_worktree_protects_the_hooks_and_the_log_of_the_main_checkout(self) -> None:
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@example.com")
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "x"], cwd=self.repo, check=True, env=env)
        tree = self.repo.parent / "wt"
        subprocess.run(["git", "worktree", "add", "-q", str(tree)], cwd=self.repo, check=True)
        for command in (f"echo x > {self.repo}/.git/hooks/pre-commit", f"echo x > {self.repo}/.agents/log/x"):
            with self.subTest(command=command):
                result = guard({"tool_input": {"command": command}, "cwd": str(tree)}, tree)
                self.assertEqual(result.returncode, 2, result.stderr)

    def test_a_rev_parse_runs_in_the_folder_after_cd(self) -> None:
        (self.repo / "sub").mkdir()
        command = 'cd .. && cp x "$(git rev-parse --git-path hooks)/x"'
        result = guard({"tool_input": {"command": command}, "cwd": str(self.repo / "sub")}, self.repo / "sub")
        self.assertEqual(result.returncode, 2, result.stderr)
        scratch = self.repo.parent / "scratch"
        subprocess.run(["git", "init", "-q", str(scratch)], check=True)
        command = f'cd {scratch} && cp hook "$(git rev-parse --show-toplevel)/.git/hooks/pre-commit"'
        self.assertEqual(self.run_command(command).returncode, 0)

    def test_a_bang_alias_is_checked(self) -> None:
        subprocess.run(["git", "config", "alias.ci", "!git commit -n"], cwd=self.repo, check=True)
        self.assertEqual(self.run_command("git ci").returncode, 2)

    def test_a_fault_of_the_guard_lets_the_call_run(self) -> None:
        env = dict(os.environ, PATH="/nonexistent")
        result = subprocess.run([sys.executable, str(SCRIPT)], text=True, capture_output=True, env=env,
                                input=json.dumps({"tool_input": {"command": "git ci -m x"}, "cwd": str(self.repo)}))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_command_forms_of_codex(self) -> None:
        self.assertEqual(self.run_command("git commit -n", key="cmd").returncode, 2)
        self.assertEqual(self.run_command(["bash", "-lc", "git commit --no-verify"]).returncode, 2)
        self.assertEqual(self.run_command(["git", "commit", "-n"]).returncode, 2)
        self.assertEqual(self.run_command(["git", "commit", "-m", "x"]).returncode, 0)

    def test_a_file_tool_may_not_write_a_protected_path(self) -> None:
        for path in (".agents/log/records/r.json", str(self.repo / ".agents/targets/required.txt"),
                     ".git/hooks/pre-commit", ".claude/settings.local.json"):
            with self.subTest(path=path):
                result = guard({"tool_name": "Write", "tool_input": {"file_path": path, "content": "x"}}, self.repo)
                self.assertEqual(result.returncode, 2)
        result = guard({"tool_name": "Edit", "tool_input": {"file_path": "src/app.py"}}, self.repo)
        self.assertEqual(result.returncode, 0)

    def test_input_that_is_not_a_tool_call_runs(self) -> None:
        for text in ("", "not json", "[]", '{"tool_input": "x"}'):
            with self.subTest(text=text):
                result = subprocess.run([sys.executable, str(SCRIPT)], input=text, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0)


@unittest.skipUnless(shutil.which("uv"), "needs uv")
class InstalledGuardTests(unittest.TestCase):
    """Copy the hooks, their settings and the gcm skill into a scratch project, as the installer does."""

    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="gate-guard-hook-test-")
        self.addCleanup(scratch.cleanup)
        self.repo = Path(scratch.name).resolve() / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.repo, check=True)
        for folder, settings in ((".claude", "settings.json"), (".codex", "hooks.json")):
            shutil.copytree(ROOT / folder / "hooks", self.repo / folder / "hooks")
            shutil.copy(ROOT / folder / settings, self.repo / folder / settings)
        shutil.copytree(ROOT / ".agents/skills/gcm", self.repo / ".agents/skills/gcm")

    def hooks(self, matcher: str):
        for adapter, settings in (("claude", ".claude/settings.json"), ("codex", ".codex/hooks.json")):
            for entry in json.loads((self.repo / settings).read_text())["hooks"].get("PreToolUse", []):
                if matcher in entry.get("matcher", "").split("|"):
                    for hook in entry["hooks"]:
                        if "gate-guard" in hook["command"]:
                            yield adapter, hook["command"]

    def run_hook(self, hook: str, payload: dict) -> subprocess.CompletedProcess:
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo))
        return subprocess.run(["sh", "-c", hook], input=json.dumps(payload), text=True, capture_output=True,
                              cwd=self.repo, env=env)

    def test_both_harnesses_stop_no_verify_and_run_a_plain_commit(self) -> None:
        found = list(self.hooks("Bash"))
        self.assertEqual(sorted(adapter for adapter, _ in found), ["claude", "codex"])
        for adapter, hook in found:
            key = "command" if adapter == "claude" else "cmd"
            with self.subTest(adapter=adapter):
                stopped = self.run_hook(hook, {"tool_input": {key: "git commit --no-verify -m x"}})
                self.assertEqual(stopped.returncode, 2, stopped.stderr)
                self.assertIn("gate guard:", stopped.stderr)
                plain = self.run_hook(hook, {"tool_input": {key: "git commit -m x"}})
                self.assertEqual((plain.returncode, plain.stdout), (0, ""), plain.stderr)

    def test_without_the_gcm_skill_the_hooks_let_the_call_run(self) -> None:
        shutil.rmtree(self.repo / ".agents/skills/gcm")
        for adapter, hook in self.hooks("Bash"):
            with self.subTest(adapter=adapter):
                result = self.run_hook(hook, {"tool_input": {"command": "git commit -n"}})
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_claude_code_checks_the_file_tools(self) -> None:
        found = list(self.hooks("Write"))
        self.assertEqual([adapter for adapter, _ in found], ["claude"])
        payload = {"tool_name": "Write", "tool_input": {"file_path": ".agents/log/records/r.json"}}
        self.assertEqual(self.run_hook(found[0][1], payload).returncode, 2)


if __name__ == "__main__":
    unittest.main()
