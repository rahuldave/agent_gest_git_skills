"""Check the gate guard of gcm: the commands that it stops, the ones that it lets run, and the installed hooks."""

from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/gcm/scripts/gate_guard.py"
_spec = importlib.util.spec_from_file_location("gate_guard", SCRIPT)
gate_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate_guard)

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
    "grep x <<< 'hello'\ngit commit -n",
    "echo $((1 << 2))\ngit commit -n",
    "echo $((x << y))\ngit commit -n",
    "cat > n.md <<'EOF'\nx\nEOF\ngit commit -n",
    "git commit -m \"doc: use <<EOF in bash\"\ngit commit -n",
    "echo x > \"$PWD/.agents/log/x\"",
    "(cd sub && ls); echo x > .agents/log/x",
    "cd /tmp; cd -; echo x > .agents/log/x",
    "GIT_CONFIG_KEY_0=core.hooksPath; git commit -m x",
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

# The commands that the guard lets run on purpose: it reads words and does not run the shell in its head. The
# commit gate has no trailer for a commit that went around it, so CI stops it there.
LEFT_TO_CI = (
    "bash <<'EOF'\ngit commit --no-verify -m x\nEOF",
    "python3 -c \"import subprocess; subprocess.run(['git', 'commit', '-n'])\"",
    "$SHELL -c 'git commit -n'",
    "git $(echo commit) -n -m x",
    "git commit -m x $(echo --no-verify)",
    "cp hook \"$(git rev-parse --git-dir)/hooks/pre-commit\"",
    "echo 'git commit -n' | bash",
    "./scripts/commit-fast.sh",
)


def guard(payload: dict, cwd: Path, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(payload), text=True, capture_output=True,
                          cwd=cwd, env=env)


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

    def test_the_forms_that_hide_git_are_left_to_ci(self) -> None:
        for command in LEFT_TO_CI:
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 0, command)

    def test_the_plain_forms_of_the_words_are_read(self) -> None:
        for command in ("ls # it's a comment\ngit commit -n", "git commit -m \"use <<EOF here\"\ngit commit -n",
                        "echo $((x << y))\ngit commit -n", "git config -f .git/config core.hooksPath h",
                        "git -c include.path=/tmp/cfg commit -m x", "echo x > \"${PWD}/.agents/log/x\"",
                        "cd /tmp; cd -; echo x > .agents/log/x", "(cd sub && ls); echo x > .agents/log/x",
                        "GIT_CONFIG_GLOBAL=/tmp/cfg git commit -m x", "git commit -m 'it\ngoes on' -n",
                        "git commit \\\n  -n -m x", "git \\\n -c core.hooksPath=/dev/null commit",
                        "cp /tmp/x \\\n .git/hooks/pre-commit", "cd .git/hooks && cp /tmp/x pre-commit",
                        "cd .git && sed -i '' s/a/b/ config", "rm -rf .agents", "mv .agents/targets /tmp/x",
                        "git commit -m x\\\\\\\n -n", "cp evil .git/config 2>/dev/null",
                        "cp evil .git/config 2> /dev/null", "mv x .agents/log/"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        for command in ("git commit -m 'unclosed", "cd \"$unknown\" && echo x > .agents/log/x",
                        "tee out.log < .git/config", "mkdir .agents", "rm -rf .agents/log-old",
                        "mv out.txt ..", "mv notes.md .agents", "git commit -m x\\\\\n -n",
                        "git config -f other.cfg user.name x", "echo x > $PWDX/.agents/log/x"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 0, command)

    def test_a_fault_of_the_guard_stops_only_a_git_line(self) -> None:
        with unittest.mock.patch.object(gate_guard, "check", side_effect=RuntimeError("fault")):
            for command, code in (("git status", 2), ("ls", 0)):
                with self.subTest(command=command), unittest.mock.patch.object(
                        sys, "stdin", io.StringIO(json.dumps({"tool_input": {"command": command}}))):
                    self.assertEqual(gate_guard.main(), code)

    def test_a_skip_asks_the_person(self) -> None:
        for command in ("just record-skip review typo", "cd sub && just --quiet record-skip review 'a typo'",
                        "uv run python .agents/skills/gcm/scripts/record_result.py skip review typo",
                        "just -f Justfile record-skip review typo", "just --justfile Justfile record-skip review x",
                        "just -d . record-skip review x", "just --set a b record-skip review x",
                        "just agent_gest_git_skills::record-skip review x", "sh -c 'just record-skip review x'"):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual(result.returncode, 0, result.stderr)
                answer = json.loads(result.stdout)["hookSpecificOutput"]
                self.assertEqual((answer["hookEventName"], answer["permissionDecision"]), ("PreToolUse", "ask"))
                self.assertIn("without the record of a fresh agent", answer["permissionDecisionReason"])

    def test_a_skip_in_codex_stops_and_names_the_person(self) -> None:
        result = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": "just record-skip review typo"}, "cwd": str(self.repo)}),
            text=True, capture_output=True, cwd=self.repo, env=dict(os.environ, JN_HOOK_HARNESS="codex"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Ask the person to run the command", result.stderr)

    def guard_in(self, harness: str, command: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.repo)}),
            text=True, capture_output=True, cwd=self.repo, env=dict(os.environ, JN_HOOK_HARNESS=harness))

    def test_only_the_harness_runs_the_record_hook(self) -> None:
        for command in ("python3 .agents/skills/gcm/scripts/record_result.py hook < event.json",
                        "echo '{}' | uv run --with pyyaml python record_result.py hook"):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual(result.returncode, 2)
                self.assertIn("only the SubagentStop hook", result.stderr)

    def test_a_word_record_that_is_not_the_recipe_runs(self) -> None:
        for command in ("just test record", "just gte record", "just --set a record test", "just --list record",
                        "just -l record", "just --dump record", "just --evaluate record",
                        "just --command echo record", "just test && echo exec done", "just test | tee env"):
            with self.subTest(command=command):
                self.assertEqual(self.guard_in("claude", command).returncode, 0, command)

    def test_a_record_line_that_names_env_only_as_text_runs_in_codex(self) -> None:
        for command in ("just record review r.txt && echo exec done", "just record review r.txt | tee env.log"):
            with self.subTest(command=command):
                self.assertEqual(self.guard_in("codex", command).returncode, 0, command)

    def test_without_just_any_word_record_counts(self) -> None:
        with unittest.mock.patch.object(gate_guard, "just_options", return_value=None):
            self.assertTrue(gate_guard.runs_record(["test", "record"]))
            self.assertFalse(gate_guard.runs_record(["test", "review"]))

    def test_the_options_of_just_come_from_just_help(self) -> None:
        options = gate_guard.just_options()
        self.assertEqual((options["-f"], options["--set"], options["--ceiling"]), (1, 2, 1))
        self.assertEqual(options["--command"], -1)

    def test_a_commit_with_a_hooks_path_from_any_source_stops(self) -> None:
        outside = Path(tempfile.mkdtemp(prefix="include-"))
        self.addCleanup(shutil.rmtree, outside)
        include = outside / "inc"
        include.write_text("[core]\n\thooksPath = /tmp/elsewhere\n")
        self.assertEqual(self.run_command("git commit -m x").returncode, 0)
        cases = (
            ("include", ["config", "include.path", str(include)]),
            ("worktree", ["config", "extensions.worktreeConfig", "true"]),
        )
        for label, setting in cases:
            with self.subTest(label=label):
                subprocess.run(["git", *setting], cwd=self.repo, check=True)
                if label == "worktree":
                    (self.repo / ".git/config.worktree").write_text("[core]\n\thooksPath = /tmp/elsewhere\n")
                for command in ("git commit -m x", "git merge feat", "git pull"):
                    result = self.run_command(command)
                    self.assertEqual(result.returncode, 2, command)
                    self.assertIn("core.hooksPath is set", result.stderr)
                subprocess.run(["git", "config", "--unset", setting[1]], cwd=self.repo, check=True)
                (self.repo / ".git/config.worktree").unlink(missing_ok=True)
        self.assertEqual(self.run_command("git commit -m x").returncode, 0)

    def hooks_folder(self, value: str = "/tmp/elsewhere") -> Path:
        """A new folder outside the repository with a config file that sets core.hooksPath to VALUE."""
        folder = Path(tempfile.mkdtemp(prefix="hooks-config-"))
        self.addCleanup(shutil.rmtree, folder)
        (folder / "cfg").write_text(f"[core]\n\thooksPath = {value}\n")
        return folder

    def test_an_empty_hooks_path_also_stops(self) -> None:
        home = self.hooks_folder("")
        (home / ".gitconfig").write_text((home / "cfg").read_text())
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / "xdg"))
        result = guard({"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}, "cwd": str(self.repo)},
                       self.repo, env)
        self.assertEqual(result.returncode, 2)
        self.assertIn(f"file:{home}/.gitconfig", result.stderr)
        subprocess.run(["git", "config", "include.path", str(home / "cfg")], cwd=self.repo, check=True)
        self.assertEqual(self.run_command("git commit -m x").returncode, 2)

    def test_a_hooks_path_from_the_global_config_or_a_variable_stops(self) -> None:
        home = self.hooks_folder()
        (home / ".gitconfig").write_text((home / "cfg").read_text())
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / "xdg"))
        result = guard({"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}, "cwd": str(self.repo)},
                       self.repo, env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("core.hooksPath is set", result.stderr)
        parameters = dict(os.environ, GIT_CONFIG_PARAMETERS="'core.hookspath'='/tmp/h'")
        result = guard({"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}, "cwd": str(self.repo)},
                       self.repo, parameters)
        self.assertEqual(result.returncode, 2)

    def test_the_check_uses_the_variables_of_the_command(self) -> None:
        folder = self.hooks_folder()
        (folder / ".gitconfig").write_text((folder / "cfg").read_text())
        cfg = folder / "cfg"
        for command in (f"GIT_CONFIG_GLOBAL={cfg} git commit -m x", f"export GIT_CONFIG_GLOBAL={cfg}; git commit",
                        f"env GIT_CONFIG_GLOBAL={cfg} git commit", f"GIT_CONFIG_SYSTEM={cfg} git commit",
                        "GIT_CONFIG_GLOBAL=$(mktemp) git commit"):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual(result.returncode, 2, command)
                self.assertIn("core.hooksPath", result.stderr)

    def test_the_variables_reach_the_nested_commands(self) -> None:
        cfg = self.hooks_folder() / "cfg"
        for command in (f"GIT_CONFIG_GLOBAL={cfg} bash -c 'git commit -qm x'",
                        f"export GIT_CONFIG_GLOBAL={cfg}; bash -c 'git commit -qm x'",
                        f"export GIT_CONFIG_GLOBAL={cfg}; eval git commit -qm x",
                        f"export GIT_CONFIG_GLOBAL={cfg}; echo $(git commit -qm x)",
                        f"declare -x GIT_CONFIG_GLOBAL={cfg}; git commit", f"typeset -x GIT_CONFIG_GLOBAL={cfg}; git commit",
                        f"GIT_CONFIG_GLOBAL={cfg} git rebase -x 'git commit --amend' main"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)

    def test_a_setting_of_git_minus_c_is_checked(self) -> None:
        cfg = self.hooks_folder() / "cfg"
        for command in (f"git -c include.path={cfg} commit -qm x", f"git -c includeIf.onbranch:main.path={cfg} commit",
                        f"export P={cfg}; git --config-env=include.path=P commit",
                        ):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        result = self.run_command("GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=$(echo core.hookspath) git commit")
        self.assertEqual(result.returncode, 2)
        self.assertIn("GIT_CONFIG_", result.stderr)
        self.assertEqual(self.run_command("git -c user.name=x commit -qm x").returncode, 0)

    def test_an_alias_is_looked_up_in_the_repository_of_the_command(self) -> None:
        other = Path(tempfile.mkdtemp(prefix="other-repo-"))
        self.addCleanup(shutil.rmtree, other)
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        subprocess.run(["git", "config", "alias.ci", "commit"], cwd=other, check=True)
        result = self.run_command(f"git -C {other} ci -qm x -n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--no-verify", result.stderr)

    def test_a_commit_in_a_folder_that_the_line_makes_runs(self) -> None:
        for command in ("mkdir -p D && cd D && git init -q && git commit --allow-empty -m init",
                        "git init -q D && git -C D commit --allow-empty -m init", "git -C /no/such/folder commit",
                        "cd ~ && cd x && git commit -m x"):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)

    def test_git_under_xargs_stops(self) -> None:
        for command in ("echo x | xargs git commit -n", "echo CFG | xargs -I{} env GIT_CONFIG_GLOBAL={} git commit -m x"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        self.assertEqual(self.run_command("printf a | xargs git add").returncode, 0)

    def test_a_function_gets_the_assignments_of_its_call(self) -> None:
        cfg = self.hooks_folder() / "cfg"
        for command in (f"f(){{ git commit -m x; }}; GIT_CONFIG_GLOBAL={cfg} f",
                        f"function f {{ git commit -m x; }}; GIT_CONFIG_GLOBAL={cfg} f"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)

    def test_an_assignment_that_is_not_exported_does_not_hide_a_hooks_path(self) -> None:
        home = self.hooks_folder()
        (home / ".gitconfig").write_text((home / "cfg").read_text())
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / "xdg"))
        for command in ("GIT_CONFIG_GLOBAL=/dev/null; git commit -m x",
                        "GIT_CONFIG_GLOBAL=/dev/null; bash -c 'git commit -m x'"):
            with self.subTest(command=command):
                result = guard({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.repo)},
                               self.repo, env)
                self.assertEqual(result.returncode, 2, command)

    def test_the_env_reaches_each_nested_command(self) -> None:
        cfg = self.hooks_folder() / "cfg"
        other = Path(tempfile.mkdtemp(prefix="alias-repo-"))
        self.addCleanup(shutil.rmtree, other)
        (other / "aliases").write_text("[alias]\n\tci = commit\n\tsh = !git commit\n")
        for command in (f"GIT_CONFIG_GLOBAL={cfg} git rebase --exec='git commit --amend' main",
                        f"GIT_CONFIG_GLOBAL={other}/aliases git ci -n -m x",
                        f"GIT_CONFIG_GLOBAL={cfg} git -c alias.sh='!git commit -m x' sh",
                        f"readonly GIT_CONFIG_GLOBAL={cfg}; git commit", f"local GIT_CONFIG_GLOBAL={cfg}; git commit"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)

    def test_an_alias_that_names_itself_runs(self) -> None:
        result = self.run_command("alias git='git -c color.ui=always'; git log")
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertEqual(self.run_command("alias git='git -c color.ui=always'; git commit -n").returncode, 2)

    def test_a_write_to_the_git_config_stops(self) -> None:
        result = self.run_command("echo '[core] hooksPath=/tmp/h' >> .git/config")
        self.assertEqual(result.returncode, 2)
        write = {"tool_name": "Edit", "tool_input": {"file_path": str(self.repo / ".git/config")}, "cwd": str(self.repo)}
        self.assertEqual(guard(write, self.repo).returncode, 2)
        self.assertEqual(self.run_command("cat .git/config").returncode, 0)

    def test_a_write_under_the_home_folder_is_checked(self) -> None:
        home = Path(tempfile.mkdtemp(prefix="home-"))
        self.addCleanup(shutil.rmtree, home)
        env = {k: v for k, v in os.environ.items() if k != "CODEX_HOME"}
        env["HOME"] = str(home)
        for command, code in (("cp a.jsonl ~/.codex/sessions/", 2), ("cp a.txt ~/notes.txt", 0)):
            with self.subTest(command=command):
                result = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(
                    {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.repo)}),
                    text=True, capture_output=True, cwd=self.repo, env=env)
                self.assertEqual(result.returncode, code, result.stderr)

    def test_record_stops_in_claude_code_and_runs_in_codex(self) -> None:
        for command in ("just record review r.txt", "python3 record_result.py record review r.txt",
                        "just -f Justfile --set a b record review r.txt", "just agent_gest_git_skills::record x y",
                        "just --ceiling / record t f", "just --group g record t f",
                        "just --justfile-name Justfile record t f", "just --dump-format json record t f",
                        "just -vf Justfile record t f", "just -nf Justfile record t f", "just -fJustfile record t f",
                        "just --justfile=Justfile record t f", "just a=b -- record t f"):
            with self.subTest(command=command):
                self.assertEqual(self.guard_in("claude", command).returncode, 2)
                self.assertEqual(self.guard_in("codex", command).returncode, 0)

    def test_a_record_command_that_changes_a_harness_variable_stops(self) -> None:
        for command in ("env -u CLAUDECODE just record review r.txt", "CODEX_HOME=/tmp/x just record review r.txt",
                        "unset CODEX_THREAD_ID; just record review r.txt",
                        "export CLAUDE_CODE_SESSION_ID= && just record-skip review x",
                "env -i PATH=/usr/bin just record review r.txt", "unset ${!CODEX_*}; just record review r.txt",
                "exec -c just record review r.txt", "export -n FOO; just record review r.txt",
                "/usr/bin/env -i PATH=/usr/bin just record t f", "'env' -i PATH=/usr/bin just record t f",
                "\"env\" -i just record t f", "e''nv -i just record t f"):
            with self.subTest(command=command):
                result = self.guard_in("codex", command)
                self.assertEqual(result.returncode, 2, command)
                self.assertIn("could write a record", result.stderr)

    def test_a_write_to_the_codex_sessions_stops(self) -> None:
        home = Path(tempfile.mkdtemp(prefix="codex-home-"))
        self.addCleanup(shutil.rmtree, home)
        for command in (f"echo x > {home}/sessions/a.jsonl", f"cp a.jsonl {home}/sessions/2026/"):
            with self.subTest(command=command):
                result = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(
                    {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.repo)}),
                    text=True, capture_output=True, cwd=self.repo, env=dict(os.environ, CODEX_HOME=str(home)))
                self.assertEqual(result.returncode, 2, command)
                self.assertIn("Codex sessions", result.stderr)

    def test_a_record_and_other_recipes_do_not_ask(self) -> None:
        for command in ("just record review result.txt", "just review", "echo just record-skip",
                        "just test", "cat record_result.py"):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""), command)

    def test_a_skip_with_a_command_that_goes_around_the_gate_stops(self) -> None:
        result = self.run_command("just record-skip review typo && git commit -n -m x")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")

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
        for command in (f"echo x > {self.repo}/.git/hooks/pre-commit", f"echo x > {self.repo}/.agents/log/x",
                        f"rm {self.repo}/.claude/settings.json", f"echo x > {self.repo}/.codex/hooks.json",
                        f"echo '[core] hooksPath=/tmp/h' >> {self.repo}/.git/config"):
            with self.subTest(command=command):
                result = guard({"tool_input": {"command": command}, "cwd": str(tree)}, tree)
                self.assertEqual(result.returncode, 2, result.stderr)
        write = {"tool_name": "Write", "tool_input": {"file_path": f"{self.repo}/.claude/settings.json"},
                 "cwd": str(tree)}
        self.assertEqual(guard(write, tree).returncode, 2)

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
