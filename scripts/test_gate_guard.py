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


def guard(payload: dict, cwd: Path, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(payload), text=True, capture_output=True,
                          cwd=cwd, env=env)


def spread(line: str) -> list:
    return gate_guard.spread_split_string(line.split())


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
                        f"HOME={folder} git commit", "HOME=$UNKNOWN git commit",
                        "GIT_CONFIG_GLOBAL=$(mktemp) git commit"):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual(result.returncode, 2, command)
                self.assertIn("core.hooksPath", result.stderr)

    def test_the_check_uses_the_repository_that_the_options_name(self) -> None:
        other = Path(tempfile.mkdtemp(prefix="other-repo-"))
        self.addCleanup(shutil.rmtree, other)
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        subprocess.run(["git", "config", "core.hooksPath", "/tmp/h"], cwd=other, check=True)
        for command in (f"git -C {other} commit -m x", f"git --git-dir={other}/.git commit",
                        f"git --git-dir {other}/.git merge feat", f"GIT_DIR={other}/.git git commit"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        # The reverse: the folder of the command has a hooks path, and the repository that -C names has none.
        result = guard({"tool_name": "Bash", "tool_input": {"command": f"git -C {self.repo} commit -m x"},
                        "cwd": str(other)}, other)
        self.assertEqual((result.returncode, result.stderr), (0, ""))

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
        for command in ("git -c \"$(echo core.hookspath)=\" commit", "k=$(echo core.hookspath); git -c \"$k=\" commit",
                        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=$(echo core.hookspath) GIT_CONFIG_VALUE_0= git commit"):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual(result.returncode, 2, command)
                self.assertIn("the guard cannot know", result.stderr)
        self.assertEqual(self.run_command("git -c user.name=x commit -qm x").returncode, 0)

    def test_a_repository_that_the_guard_cannot_reach_stops(self) -> None:
        for command, reason in (("git -C \"$(echo /x)\" commit -qm x", "cannot know"),
                                ("cd \"$(echo /x)\" && git commit -qm x", "cannot know")):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual(result.returncode, 2, command)
                self.assertIn(reason, result.stderr)

    def test_an_alias_is_looked_up_in_the_repository_of_the_command(self) -> None:
        other = Path(tempfile.mkdtemp(prefix="other-repo-"))
        self.addCleanup(shutil.rmtree, other)
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        subprocess.run(["git", "config", "alias.ci", "commit"], cwd=other, check=True)
        result = self.run_command(f"git -C {other} ci -qm x -n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--no-verify", result.stderr)

    def test_the_older_parse_gaps_are_closed(self) -> None:
        for command in ("A+=1 git commit -qm x -n", "env -S 'git commit -qm x -n'", "env -S'git commit -n'",
                        "env --split-string='git commit -n'"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)

    def test_the_static_checks_run_before_the_hooks_path(self) -> None:
        with unittest.mock.patch.object(gate_guard, "hooks_path_set", side_effect=RuntimeError):
            with self.assertRaises(gate_guard.Blocked):
                gate_guard.check_command("git commit -n -m x", str(self.repo))

    def test_a_config_that_git_cannot_read_stops(self) -> None:
        (self.repo / ".git/config").write_text("[core\n")
        result = self.run_command("git commit -m x")
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot read", result.stderr)
        for error in (subprocess.TimeoutExpired("git", 5), OSError("no git")):
            with self.subTest(error=error), unittest.mock.patch.object(gate_guard.subprocess, "run", side_effect=error):
                self.assertTrue(gate_guard.hooks_path_set(str(self.repo), [], {}).startswith("?"))

    def test_a_commit_in_a_folder_that_the_line_makes_runs(self) -> None:
        for command in ("mkdir -p D && cd D && git init -q && git commit --allow-empty -m init",
                        "git init -q D && git -C D commit --allow-empty -m init", "git -C /no/such/folder commit",
                        "cd ~ && cd x && git commit -m x"):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)

    def test_a_fault_of_the_guard_stops_a_git_line(self) -> None:
        result = self.run_command("echo $__substitution9__; git commit -n -m x")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(gate_guard.expand("$__substitution9__", {}, [], "/"), "$__substitution9__")
        with unittest.mock.patch.object(gate_guard, "check", side_effect=RuntimeError("fault")):
            for command, code in (("git status", 2), ("ls", 0)):
                with self.subTest(command=command), unittest.mock.patch.object(
                        sys, "stdin", io.StringIO(json.dumps({"tool_input": {"command": command}}))):
                    self.assertEqual(gate_guard.main(), code)

    def test_a_word_that_the_shell_changes_stops_a_commit(self) -> None:
        for command in ("git commit -m x $(echo --no-verify)", "git commit -m x $'--no-verify'",
                        "git commit -m x {--no-verify,}", "git commit -m x ${u:---no-verify}",
                        "git $(echo commit) -n -m x", "git merge `echo --no-verify` feat"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        for command in ('git commit -m "$msg"', 'git commit -F "$f"', 'git commit -m x -- "$f"',
                        'git commit --message="$m"', 'git commit --message "$m"', 'git commit -am "$m"', 'git merge -m "$m" feat'):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)

    def test_git_under_xargs_stops(self) -> None:
        for command in ("echo --no-verify | xargs git commit -m x", "printf '%s\\n' commit | xargs git",
                        "echo CFG | xargs -I{} env GIT_CONFIG_GLOBAL={} git commit -m x"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        self.assertEqual(self.run_command("printf a | xargs git add").returncode, 0)

    def test_a_variable_set_by_a_builtin_is_unknown(self) -> None:
        for command in ("read GIT_CONFIG_GLOBAL <<< CFG; export GIT_CONFIG_GLOBAL; git commit -m x",
                        "printf -v GIT_CONFIG_GLOBAL %s CFG; export GIT_CONFIG_GLOBAL; git commit -m x",
                        "for GIT_CONFIG_GLOBAL in CFG; do export GIT_CONFIG_GLOBAL; git commit -m x; done",
                        "mapfile GIT_CONFIG_COUNT < f; git commit -m x"):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual(result.returncode, 2, command)
                self.assertIn("cannot know", result.stderr)

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

    def test_env_with_s_in_a_cluster_is_split(self) -> None:
        cfg = self.hooks_folder() / "cfg"
        for command in ("env -vS 'git commit -n -m x'", f"env -iS 'GIT_CONFIG_GLOBAL={cfg} git commit -m x'",
                        f"env -S 'GIT_CONFIG_GLOBAL={cfg} git commit -m x'"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        self.assertEqual(spread("env -u S git commit -mSx"), ["env", "-u", "S", "git", "commit", "-mSx"])
        self.assertEqual(spread("env -uS git status"), ["env", "-uS", "git", "status"])
        self.assertEqual(gate_guard.spread_split_string(["env", "-iSgit commit -n"]), ["env", "-i", "git", "commit", "-n"])
        self.assertEqual(gate_guard.spread_split_string(["env", "-vS", "git commit -n"]),
                         ["env", "-v", "git", "commit", "-n"])
        self.assertEqual(gate_guard.spread_split_string(["env", "A=1", "--split-string=git x"]),
                         ["env", "A=1", "git", "x"])

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

    def test_the_values_of_the_options_are_those_of_each_command(self) -> None:
        for command in ("git commit -s $X -m x", "git pull -t $X origin main", "git merge --squash $X feat"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        for command in ('git commit -s -m "$m"', 'git merge -s "$s" -m x feat', 'git pull -X "$o" origin main'):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)

    def test_a_pattern_of_file_names_stops_a_commit(self) -> None:
        for command in ("git commit -m x --no-veri*", "git commit -m x --no-ver[i]fy", "git commit -m x -?"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        self.assertEqual(self.run_command("git commit -m 'fix *.py' -- '*.py'").returncode, 0)

    def test_git_after_a_program_that_runs_it_is_checked(self) -> None:
        for command in ("arch -arm64 git commit -n -m x", "find . -maxdepth 0 -exec git commit --no-verify -m x \\;",
                        "caffeinate -i git commit -n", "stdbuf -o0 git commit -n", "uv run git commit -n",
                        "git submodule foreach 'git commit -n'", "git submodule --quiet foreach --recursive 'git commit -n'"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        for command in ("echo git commit -n", "grep -rn git commit", "uv run git status", "ls git"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 0, command)

    def test_a_program_that_the_shell_changes_stops_a_git_line(self) -> None:
        for command in ("$(command -v git) commit --no-verify -m x", "`which git` commit -n", "${G:-git} commit -n",
                        '$SHELL -c "git commit -n"'):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual(result.returncode, 2, command)
                self.assertNotIn("__substitution", result.stderr)
        self.assertEqual(self.run_command("$EDITOR notes.txt").returncode, 0)

    def test_a_git_line_nested_too_deeply_stops(self) -> None:
        for command in ("echo $(echo $(echo $(echo $(echo $(git commit -n -m x)))))", "eval eval eval eval eval git commit -n"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        self.assertEqual(self.run_command("echo $(echo $(echo $(echo $(echo $(ls)))))").returncode, 0)

    def test_an_alias_of_the_shell_is_followed(self) -> None:
        for command in ('alias g="git commit --no-verify"; eval g -m x', "alias g='git commit'; g -n -m x"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        self.assertEqual(self.run_command("alias ll='ls -l'; ll").returncode, 0)

    def test_foreach_keeps_the_options_of_its_command(self) -> None:
        for command in ("git submodule foreach git commit -n -m x", "git submodule foreach git commit --no-verify -m x",
                        "git submodule foreach --recursive git commit -n", "git submodule foreach sh -c 'git commit -n'",
                        "git submodule foreach --quiet 'git commit -n'"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        self.assertEqual(self.run_command("git submodule foreach git status -s").returncode, 0)

    def test_each_git_word_after_a_program_is_checked(self) -> None:
        for command in ("uv run --with git git commit -n -m x", "strace -o git git commit -n",
                        "find . -name git -exec git commit -n -m x \\;", "uv run bash -c 'git commit -n -m x'"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        for command in ("ack git *.py", "find . -name git -o -name '*.py'", "test -d git && git status",
                        "alias x='echo'; x git commit -n"):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)

    def test_an_opaque_program_that_could_be_git_stops(self) -> None:
        for command in ("$(echo git) -c alias.x='commit -n' x", "/usr/bin/gi? -c alias.x='commit --no-verify' x",
                        "$(echo git) ci -n -m x", "X='git commit -n'; $X", "/usr/bin/gi? ci -n -m x",
                        "$G -c alias.x='commit -n' x"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        for command in ('"$PYTHON" -m pytest tests/test_git.py', "$EDITOR .gitignore", '"$VENV/bin/ruff" check .github'):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)

    def test_an_attached_value_does_not_hide_the_next_word(self) -> None:
        for command in ("git commit --message=x $X", "git commit -mx $X", "git commit -S$K $X", "git commit -Sk $X",
                        "git commit -Sm $X"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)

    def test_an_opaque_program_gets_the_checks_of_git(self) -> None:
        for command in ("${X:-git} config core.hooksPath /tmp/h", "${X:-git} rebase -x 'git commit -n' HEAD~1",
                        "${X:-git} $C -n -m x", "$X commit-tree HEAD^{tree}", "$X submodule foreach 'git commit -n'", "$X commit -n -m x"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        for command in ('"$PYTHON" -m pytest -k commit', "$PY -m unittest x.py -k merge",
                        '"$VIRTUAL_ENV/bin/python" manage.py pull', "${PYTHON:-python3} -m pytest -k merge",
                        '"$(git rev-parse --show-toplevel)/scripts/check.sh"',
                        '"$(dirname "$(git rev-parse --git-dir)")/x.sh"', "$CC -c foo.c"):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)
        self.assertEqual(self.run_command('"$VENV/bin/uv" run git commit -n').returncode, 2)

    def test_a_variable_with_spaces_is_split_at_any_depth(self) -> None:
        line = 'X="git commit -n"; $X'
        for depth in range(6):
            with self.subTest(depth=depth):
                self.assertEqual(self.run_command(line).returncode, 2, line)
            line = "eval " + shlex.quote(line)

    def test_a_shell_option_before_c_is_skipped(self) -> None:
        for command in ("$SHELL -o pipefail -c 'git commit -n'", "$SHELL --norc -c 'git commit -n'",
                        '"$SHELL" -e -c "git commit -n"', "uv run bash -e -c 'git commit -n'",
                        "uv run bash --norc -c 'git commit -n'", "bash -O extglob -c 'git commit -n'",
                        "uv run bash <<'E'\ngit commit -n -m x\nE"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)

    def test_an_opaque_subcommand_after_a_program_stops(self) -> None:
        for command in ("uv run git $C -n -m x", "xcrun git $C -n", "find . -exec git $C -n -m x \\;"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)

    def test_an_alias_that_names_itself_runs(self) -> None:
        result = self.run_command("alias git='git -c color.ui=always'; git log")
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertEqual(self.run_command("alias git='git -c color.ui=always'; git commit -n").returncode, 2)

    def test_an_opaque_program_that_runs_git_is_scanned(self) -> None:
        for command in ("$UV run git commit -n -m x", "${UV:-uv} run git commit --no-verify -m x",
                        "${X:-/usr/bin/git} commit -n", "${X-/usr/bin/git} commit -n"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        result = self.run_command("${PYTHON:-/usr/bin/python3} -m pytest -k commit")
        self.assertEqual((result.returncode, result.stderr), (0, ""))

    def test_the_text_of_a_shell_is_the_first_word_after_its_options(self) -> None:
        for command in ("bash -c -x 'git commit -n -m x'", "bash -c -- 'git commit -n'", "sh -c -e 'git commit -n'",
                        "uv run bash -c -x 'git commit -n'", "bash -lc 'git commit -n'"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        self.assertEqual(gate_guard.shell_text(["-o", "pipefail", "-c", "T"]), "T")
        self.assertEqual(gate_guard.shell_text(["-ec", "T"]), "T")
        self.assertEqual(gate_guard.shell_text(["-c", "--", "-x"]), "-x")
        self.assertIsNone(gate_guard.shell_text(["script.sh", "-c", "T"]))
        self.assertEqual(self.run_command("bash script.sh -c 'git commit -n'").returncode, 0)

    def test_only_a_pattern_option_lets_an_opaque_word_after_git(self) -> None:
        for command in ("uv run --frozen git $C -n -m x", "arch -arm64 git $C -n -m x", "uv run -- git $C -n -m x"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        self.assertEqual(self.run_command("find . -name git -o -name '*.py'").returncode, 0)

    def test_fd_that_runs_git_is_checked(self) -> None:
        for command in ("fd -x git commit -n -m x", "fd --exec git commit --no-verify", "fd -X git commit -n"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        self.assertEqual(self.run_command("fd git").returncode, 0)

    def test_the_here_doc_of_an_opaque_shell_is_checked(self) -> None:
        for command in ("$SHELL <<'E'\ngit commit -n -m x\nE", "\"$SHELL\" -s <<'E'\ngit commit -n -m x\nE"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)

    def test_only_the_program_word_makes_a_here_doc_shell(self) -> None:
        body = "\nDo not run git commit -n here.\nEOF"
        for command in ("cat > \"$OUT\" <<'EOF'", 'tee "$F" <<EOF', "git commit -m \"$T\" -F - <<'EOF'",
                        'gh pr create --title "$TITLE" --body-file - <<EOF', 'gh pr create --title "fix [gate]" <<EOF',
                        'uv run --project "$P" python - <<EOF'):
            with self.subTest(command=command):
                result = self.run_command(command + body)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)
        for command in ('"$SH" <<EOF', "${SH:-/bin/sh} <<EOF"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command + body).returncode, 2, command)

    def test_a_cluster_with_o_takes_its_value(self) -> None:
        for cluster in ("-oc errexit", "-co errexit", "-cO extglob", "-Oc extglob", "-eoc errexit"):
            for program in ("bash", "$UV run bash", '"$SH"', "zsh"):
                command = f"{program} {cluster} 'git commit -n -m x'"
                with self.subTest(command=command):
                    self.assertEqual(self.run_command(command).returncode, 2, command)

    def test_a_default_path_of_git_with_an_opaque_subcommand_stops(self) -> None:
        for command in ("${X:-/usr/bin/git} $C -n -m x", '${X:-"/usr/bin/git"} $C -n',
                        "find . -name '*.py' -exec $G commit -n \\;"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)

    def test_a_prefix_after_exec_does_not_hide_an_opaque_program(self) -> None:
        for command in ("find . -exec env $G commit -n -m x \\;", "find . -exec nice $G commit -n \\;",
                        "find . -exec sudo $G commit -n \\;", "find . -exec command $G commit -n \\;",
                        "fd -x env $G commit -n", "fd --exec=$G commit -n"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        for command in ("find . -exec $D/bin/tool commit -n \\;", 'find . -exec "$PY" "$SCRIPT" {} \\;'):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)

    def test_the_reader_of_a_here_doc_is_found_on_either_side(self) -> None:
        body = "\ngit commit -n -m x\nE"
        for command in ("<<'E' bash", "cat <<'E' | bash", 'cat <<E | "$SHELL"', "cat <<E |& sh -s"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command + body).returncode, 2, command)
        for command in ("gh issue create --title bash --body-file - <<'E'", "cat <<'E' | grep bash",
                        "\"$VENV/bin/python\" - <<'E'", "cat <<'E' > out.sh"):
            with self.subTest(command=command):
                result = self.run_command(command + body)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)

    def test_a_here_doc_whose_reader_is_hard_to_see_is_shell(self) -> None:
        for command in ("cat <<EOF |\ngit commit -n -m x\nEOF\nbash", "cat <<EOF \\\n  | bash\ngit commit -n -m x\nEOF",
                        "cat <<EOF |(bash)\ngit commit -n -m x\nEOF", "cat <<EOF | (bash)\ngit commit -n -m x\nEOF",
                        "SH=bash; uv run $SH <<EOF\ngit commit -n -m x\nEOF", "uv run /bin/b?sh <<EOF\ngit commit -n\nEOF",
                        "A=1 <<EOF bash\ngit commit -n\nEOF", "uv <<EOF run bash\ngit commit -n\nEOF",
                        "uv run $SH -c 'git commit -n -m x'"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        for command in ("cat <<EOF > x.txt; ls | sh\ngit commit -n\nEOF", 'git -C . commit -F - <<EOF\n-n\nEOF', 'uv run --project "$P" python - <<EOF\ngit commit -n\nEOF',
                        "uv run pytest -x $T -k commit -n 4", "cat <<EOF | tee out.md\ngit commit -n\nEOF"):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)

    def test_the_pipe_of_a_here_doc_follows_quotes_and_lines(self) -> None:
        body = "\ngit commit -n -m x\nE"
        for command in ("cat <<E | sed 's/a/b/;s/c/d/' | bash", 'cat <<E | tr ";" " " | sh', 
                        "uv run --python 3.12 $SH <<E", "stdbuf -oL $SH <<E", "caffeinate $SH <<E", "stdbuf $SH <<E",
                        "pixi exec $SH <<E", "uvx -- $SH <<E"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command + body).returncode, 2, command)
        for command in ("cat <<E |&\ngit commit -n -m x\nE\nbash", "cat <<E |\ngit commit -n -m x\nE\nbash"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        result = self.run_command("cat <<E | tee \\\n .agents/log/records/r.json\n{}\nE")
        self.assertEqual(result.returncode, 2)
        for command in ("cat <<'E' | jq . \\\n > out.json\ngit commit -n\nE", "cat <<'E' | jq '.a; .b'\ngit commit -n\nE",
                        'uv run --project "$P" python - <<E\ngit commit -n\nE'):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)

    def test_fd_under_a_runner_runs_its_exec_option(self) -> None:
        for command in ("uv run fd -x $G commit -n -m x", "fdfind -x $G commit -n", "caffeinate -i fd . -X $G commit -n"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        self.assertEqual(self.run_command("uv run pytest -x $T -k commit -n 4").returncode, 0)

    def test_the_pipe_scan_reads_redirections_quotes_and_backslashes(self) -> None:
        body = "\ngit commit -n -m x\nEOF"
        for command in ("bash -s <<EOF x\\\\", "cat <<EOF 2>&1 | bash", "cat <<EOF >&2 | bash", "cat <<EOF &>/dev/null | bash",
                        "cat <<EOF 0<&0 | bash", 'cat <<EOF - "x\\"" | bash', "cat <<EOF | b\\ash",
                        'uv run --no-sync "$SHELL" <<EOF', "uv run --isolated $SH <<EOF", "cat <<EOF \\; | bash"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command + body).returncode, 2, command)
        for command in ("cat <<EOF & bash -c true", "cat <<EOF & echo hi | bash", 'uv run --project "$P" python - <<EOF'):
            with self.subTest(command=command):
                result = self.run_command(command + body)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)

    def test_comments_substitutions_and_runner_values_in_here_docs(self) -> None:
        body = "\ngit commit -n -m x\nEOF"
        for command in ("uv run --no-sync $SHELL /dev/stdin <<EOF", "cat <<EOF | uv run --isolated \"$SH\" -s x",
                        "uv run --no-sync \"$SH\" -c 'bash' <<EOF", "uv run -- \"$SH\" x <<EOF", "bash <<EOF # \\",
                        "cat <<EOF ${x//&/} | bash", "cat <<EOF $(true&) | bash", "cat <<EOF $(true;) | bash",
                        "cat <<EOF `true;` | bash", "cat <<EOF $'\\'' | bash", 'nice --adjustment 5 "$SH" <<EOF',
                        "env -i $SH <<EOF"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command + body).returncode, 2, command)
        self.assertEqual(self.run_command("echo hi # note \\\ngit commit -n -m x").returncode, 2)
        for command in ('uv run --project "$P" python - <<EOF', 'uv run --with "$PKG" pytest <<EOF',
                        "cat <<EOF $(date) > out.txt"):
            with self.subTest(command=command):
                result = self.run_command(command + body)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)

    def test_quotes_carry_across_lines(self) -> None:
        self.assertEqual(gate_guard.scan_quotes("echo $'it\\'s' # x"), (None, 14))
        self.assertEqual(gate_guard.split("echo $'a b' c"), ["echo", "a b", "c"])
        for command in ("echo 'a\nb' # \\\ngit commit --no-verify -m x", 'x="a\nb" # \\\ngit commit -n',
                        "echo $'it\\'s' # \\\ngit commit -n", "cat <<EOF $(true $'\\'') | bash\ngit commit -n\nEOF",
                        "cat <<EOF $(case x in a) true;; esac) | bash\ngit commit -n\nEOF",
                        "cat <<EOF $( (true) ; ) | bash\ngit commit -n\nEOF", "echo $'it\\'s'; git commit -n"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        for command in ("git commit -m 'fix: a#b' \\\n  --allow-empty", "nice --adjustment \"$N\" python x <<EOF\ngit commit -n\nEOF",
                        "git commit -m 'line one\nDo not git commit -n here'", "echo $'a\\tb'"):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)

    def test_ansi_quotes_substitutions_in_quotes_and_escaped_comments(self) -> None:
        for command in ("bash -c $'git commit -n -m x'", "sh -c $'git commit --no-verify -m x'", "eval $'git commit -n -m x'",
                        "find . -exec sh -c $'git commit -n' \\;", "X=$'git commit -n'; $X", "bash -c $'\\x67it commit -n'",
                        "X=\"$(echo '\")' x' ) <<EOF\n')\"; git commit --no-verify -m x\nEOF",
                        "echo \\;# ; git commit --no-verify -m x", "echo \\ # ; git commit --no-verify -m x",
                        "echo 'a \\\n'; git commit -n", "bash <<<'git commit -n'", "bash <<< \"git commit -n\""):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        for command in ("cat <<'EOF' > docs/test-case.md\ngit commit --no-verify\nEOF",
                        "git commit -F - <<'EOF'  # lower-case\ngit commit -n\nEOF",
                        "git commit -m \"$(cat <<'EOF'\nFix the check of git commit -n\nEOF\n)\"",
                        "printf $'a\\nb\\n'", "git log --format=$'%h\\t%s'"):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)
        self.assertEqual(gate_guard.scan_quotes('x="$(echo \'")\' x\' )'), (('"', "$(", "'"), None))
        self.assertEqual(gate_guard.scan_quotes("echo \\;# x"), (None, None))
        self.assertEqual(gate_guard.scan_quotes('x="it' + "'" + 's"'), (None, None))
        self.assertEqual(gate_guard.scan_quotes('(#x'), (None, 1))
        body = 'cat <<E "a' + chr(92) + '\nb" | bash # ' + chr(92) + '\ngit commit -n\nE'
        self.assertEqual(gate_guard.without_heredocs(body)[1], ['git commit -n'])
        result = self.run_command('cat <<EOF > notes.md "x case a in b"\ngit commit -n\nEOF')
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertEqual(gate_guard.ansi_value("\\x67it\\n\\101\\u00e9"), "git\nAé")

    def test_a_here_doc_in_a_line_that_starts_inside_a_quote_is_text(self) -> None:
        self.assertEqual(self.run_command("echo 'a\nb <<EOF'\ngit commit -n -m x").returncode, 2)
        lines, bodies = gate_guard.without_heredocs("echo 'a\nb <<EOF'\nls")
        self.assertEqual(bodies, [])
        self.assertIn("ls", lines)

    def test_decoding_edges_comments_here_strings_and_substitutions(self) -> None:
        for command in ("$'\\x67it' commit -n -m x $'\\z'", "echo $'\\U00110000'; $'\\x67it' commit -n",
                        "git commit $'--no-verify\\0zz' -m x", "git commit $'--no-verify\\x00zz' -m x",
                        "git commit $'--no-verify\\c@zz' -m x", "x=\"$(echo '\"')\"; echo ' #'; git commit -n",
                        "x=\"`echo '\"'`\"; echo ' #'; git commit -n", "bash <<< 'echo hi' <<< 'git commit -n'",
                        "ls $(echo ')'); git commit -n", "ls `echo '`'`; git commit -n"):
            with self.subTest(command=command):
                self.assertEqual(self.run_command(command).returncode, 2, command)
        for command in ("git commit -m $'fix\\(x\\)'", "git log --grep=$'\\s'",
                        "cat <<EOF > f.txt; echo case x in y\ngit commit -n\nEOF",
                        "cat <<EOF > f.txt && grep -q x f.txt || case $? in 1) echo none;; esac\ngit commit -n\nEOF"):
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertEqual((result.returncode, result.stderr), (0, ""), command)
        self.assertEqual(gate_guard.ansi_value("a\\zb\\0c"), "a\\zb")
        self.assertEqual(gate_guard.ansi_value("\\U00110000"), "\\U00110000")
        self.assertEqual(self.run_command("ls # it's\ngit commit -n\necho '").returncode, 2)
        self.assertEqual(gate_guard.scan_quotes('x="`echo \'"\'`"'), (None, None))
        self.assertFalse(gate_guard.continues("x=\"$(echo 'a \\"))
        with unittest.mock.patch.object(gate_guard, "check", side_effect=RuntimeError("fault")), unittest.mock.patch.object(
                sys, "stdin", io.StringIO(json.dumps({"tool_input": {"command": "$'\\x67it' commit -n"}}))):
            self.assertEqual(gate_guard.main(), 2)

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
