"""Check the records of the agentic targets: `record_result.py hook`, `record` and `skip`, in scratch repositories.

The tests need pyyaml, as the recipes do: `uv run --no-project --with pyyaml python -m unittest
scripts/test_record_result.py`.
"""

from __future__ import annotations

import errno
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".agents/skills/gcm/scripts"
SCRIPT = SCRIPTS / "record_result.py"
HARNESS = ("CLAUDE_CODE_SESSION_ID", "CLAUDECODE", "CODEX_THREAD_ID", "CODEX_HOME")


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(*args: str, cwd: Path, env=None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout


def result(nonce: str, target: str = "review", status: str = "success", findings: str = "[]") -> str:
    return (f"<<<AGENT_RESULT v1>>>\ntarget: {target}\nnonce: {nonce}\nstatus: {status}\noutputs:\n"
            f"  findings: {findings}\nverification: []\nnotes: none\nfollow_up: []\n<<<END_AGENT_RESULT>>>\n")


@unittest.skipUnless(shutil.which("jagt"), "needs jagt")
class RecordTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="record-result-test-")
        self.addCleanup(scratch.cleanup)
        self.base = Path(scratch.name).resolve()
        self.repo = self.base / "proj"
        self.repo.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k not in HARNESS}
        self.env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
                        GIT_COMMITTER_EMAIL="t@example.com")
        # The settings of the person can hold the record hook, so each test has a home of its own.
        self.home = self.base / "home"
        self.home.mkdir()
        self.env["HOME"] = str(self.home)
        git("init", "-q", "-b", "main", cwd=self.repo)
        self.write(".agents/skills/grv/references/targets/review.md", "BASE TASK\n")
        self.write(".gitignore", ".agents/log/\n")
        self.write("a.txt", "a\n")
        git("add", "-A", cwd=self.repo, env=self.env)
        git("commit", "-q", "-m", "x", cwd=self.repo, env=self.env)
        self.write("a.txt", "b\n")

    def write(self, path: str, text: str, folder=None) -> Path:
        target = (folder or self.repo) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return target

    def render(self, target: str = "review", cwd=None) -> str:
        run = subprocess.run([sys.executable, SCRIPTS / "agentic_target.py", "render", target], cwd=cwd or self.repo,
                             capture_output=True, text=True, env=self.env)
        self.assertEqual(run.returncode, 0, run.stderr)
        return next(line.split(":", 1)[1].strip() for line in run.stdout.splitlines() if line.startswith("nonce:"))

    def run_script(self, *args: str, stdin="", env=None, cwd=None) -> subprocess.CompletedProcess:
        data = stdin if isinstance(stdin, bytes) else stdin.encode()
        run = subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd or self.repo, input=data, capture_output=True,
                             env=env or self.env)
        return subprocess.CompletedProcess(run.args, run.returncode, run.stdout.decode(errors="replace"),
                                           run.stderr.decode(errors="replace"))

    def hook(self, event: dict, cwd=None) -> subprocess.CompletedProcess:
        event.setdefault("cwd", str(cwd or self.repo))
        return self.run_script("hook", stdin=json.dumps(event), cwd=cwd)

    def records(self) -> list:
        folder = self.repo / ".agents/log/records"
        return [json.loads(path.read_text()) for path in sorted(folder.glob("*.json"))] if folder.is_dir() else []

    def test_the_hook_writes_a_record_that_the_gate_counts(self) -> None:
        nonce = self.render()
        run = self.hook({"last_assistant_message": "Done.\n" + result(nonce, findings='[{summary: s, test: t}]')})
        self.assertEqual(run.returncode, 0)
        self.assertIn("record: wrote", run.stderr)
        [record] = self.records()
        gate = load("commit_gate")
        self.assertEqual((record["source"], record["nonce"]), ("hook", nonce))
        self.assertTrue(gate.record_counts(record))
        self.assertEqual(gate.missing_targets(["review"], self.records(), gate.worktree_tree(self.repo)), [])

    def test_the_output_tree_holds_the_changes_of_the_fresh_agent(self) -> None:
        self.write(".agents/skills/gdo/references/targets/update-docs.md", "DOCS TASK\n")
        nonce = self.render("update-docs")
        self.write("a.txt", "c\n")
        text = result(nonce, target="update-docs").replace("  findings: []", "  files: []\n  checked: []")
        run = self.hook({"last_assistant_message": text})
        self.assertEqual(run.returncode, 0, run.stderr)
        [record] = self.records()
        gate = load("commit_gate")
        self.assertEqual(record["output_tree"], gate.worktree_tree(self.repo))
        self.assertNotEqual(record["input_tree"], record["output_tree"])
        self.assertEqual(gate.missing_targets(["update-docs"], self.records(), record["output_tree"]), [])
        # A review of the old tree does not count for the new one.
        self.assertEqual(gate.missing_targets(["review"], self.records(), record["output_tree"]), ["review"])

    def test_the_hook_reads_the_result_of_a_handback_from_the_transcript(self) -> None:
        nonce = self.render()
        transcript = self.base / "agent.jsonl"
        call = {"type": "tool_use", "name": "SubagentHandback", "input": {"message": result(nonce)}}
        transcript.write_text(json.dumps({"message": {"model": "claude-opus-5-5", "content": [call]}}) + "\n")
        run = self.hook({"last_assistant_message": "I handed back.", "agent_transcript_path": str(transcript)})
        self.assertEqual(run.returncode, 0, run.stderr)
        [record] = self.records()
        self.assertEqual(record["model"], "claude-opus-5-5")

    def test_the_hook_never_stops_the_fresh_agent(self) -> None:
        nonce = self.render()
        for text in ("not json", json.dumps([1]), json.dumps({"last_assistant_message": "no result"}),
                     json.dumps({"last_assistant_message": result("b" * 32), "cwd": str(self.repo)}),
                     json.dumps({"last_assistant_message": result(nonce, target="prose"), "cwd": str(self.repo)}),
                     json.dumps({"last_assistant_message": result(nonce), "cwd": str(self.base / "gone")}),
                     b"\xff\xfe not utf-8", json.dumps({"last_assistant_message": "x", "agent_transcript_path": 7})):
            with self.subTest(text=text[:40]):
                run = self.run_script("hook", stdin=text)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertNotIn("Traceback", run.stderr)
        # A cwd that is not a string falls back to the folder of the hook, here outside the repository.
        run = self.run_script("hook", stdin=json.dumps({"last_assistant_message": result(nonce), "cwd": 5}),
                              cwd=self.base)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn("Traceback", run.stderr)
        self.assertEqual(self.records(), [])

    def test_findings_that_the_gate_cannot_see_give_no_record(self) -> None:
        nonce = self.render()
        for text in (result(nonce, findings="{summary: SQL injection, severity: high}"),
                     result(nonce, findings="a string"),
                     result(nonce).replace("follow_up: []", "follow_up: []\nfindings: [{summary: s}]")):
            with self.subTest(text=text[60:120]):
                run = self.hook({"last_assistant_message": text})
                self.assertIn("no record of this result", run.stderr)
        self.assertEqual(self.records(), [])

    def test_one_result_of_a_packet_gives_one_record(self) -> None:
        nonce = self.render()
        self.assertIn("record: wrote", self.hook({"last_assistant_message": result(nonce)}).stderr)
        later = result(nonce, findings="[{summary: s, reason: r}]")
        self.assertIn("exists already", self.hook({"last_assistant_message": later}).stderr)
        [record] = self.records()
        self.assertEqual(record["findings"], [])
        self.assertEqual([p.name for p in (self.repo / ".agents/log/records").iterdir()], [f"{nonce}.json"])

    def test_a_file_system_with_no_hard_links_gets_a_record(self) -> None:
        module = load("record_result")
        folder = self.repo / ".agents/log/records"
        with unittest.mock.patch.object(module.os, "link", side_effect=OSError(errno.EPERM, "no links")):
            module.write_record(self.repo, {"version": 1}, "n1", once=True)
            with self.assertRaises(module.Stop):
                module.write_record(self.repo, {"version": 1}, "n1", once=True)
        self.assertEqual(json.loads((folder / "n1.json").read_text()), {"version": 1})
        self.assertEqual([p.name for p in folder.iterdir()], ["n1.json"])

    def test_a_failed_write_with_no_hard_links_leaves_no_half_record(self) -> None:
        module = load("record_result")
        folder = self.repo / ".agents/log/records"
        self.write(".agents/log/.gitignore", "*\n")  # So the first write is the temporary file, the second the record.
        real, calls = module.os.fdopen, []

        class Full:
            """A file whose write puts one byte on disk, then fails as on a full disk."""
            def __init__(self, handle):
                self.handle = handle

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.handle.close()

            def write(self, text):
                self.handle.write(text[:1])
                self.handle.flush()
                raise OSError(errno.ENOSPC, "No space left on device")

        def fdopen(fd, *args, **kwargs):
            calls.append(fd)
            handle = real(fd, *args, **kwargs)
            return Full(handle) if len(calls) == 2 else handle  # The second write is the one of the final name.

        with unittest.mock.patch.object(module.os, "link", side_effect=OSError(errno.EPERM, "no links")), \
                unittest.mock.patch.object(module.os, "fdopen", fdopen), self.assertRaises(module.Stop):
            module.write_record(self.repo, {"version": 1}, "n2", once=True)
        self.assertEqual(list(folder.iterdir()), [])
        # A later try writes the record.
        with unittest.mock.patch.object(module.os, "link", side_effect=OSError(errno.EPERM, "no links")):
            module.write_record(self.repo, {"version": 1}, "n2", once=True)
        self.assertEqual([p.name for p in folder.iterdir()], ["n2.json"])

    def test_a_result_that_jagt_refuses_gives_no_record(self) -> None:
        nonce = self.render()
        run = self.hook({"last_assistant_message": result(nonce, status="maybe")})
        self.assertIn("jagt result lint refused", run.stderr)
        self.assertEqual(self.records(), [])

    def test_a_record_from_a_worktree_goes_to_the_shared_log(self) -> None:
        tree = self.base / "wt"
        git("worktree", "add", "-q", "-b", "feat", str(tree), cwd=self.repo)
        nonce = self.render(cwd=tree)
        self.write("a.txt", "wt\n", folder=tree)
        run = self.hook({"last_assistant_message": result(nonce)}, cwd=tree)
        self.assertEqual(run.returncode, 0, run.stderr)
        [record] = self.records()
        self.assertEqual(record["output_tree"], load("commit_gate").worktree_tree(tree))
        self.assertFalse((tree / ".agents/log").exists())

    def test_a_packet_of_another_repository_gives_no_record(self) -> None:
        nonce = self.render()
        packet = self.repo / f".agents/log/packets/{nonce}.json"
        other = self.base / "other"
        other.mkdir()
        git("init", "-q", "-b", "main", cwd=other)
        data = json.loads(packet.read_text())
        data["worktree"] = str(other)
        packet.write_text(json.dumps(data))
        run = self.hook({"last_assistant_message": result(nonce)})
        self.assertIn("is not a worktree of this repository", run.stderr)
        self.assertEqual(self.records(), [])

    def test_record_writes_an_agent_record_in_another_harness(self) -> None:
        nonce = self.render()
        file = self.write("result.txt", result(nonce), folder=self.base)
        run = self.run_script("record", "review", str(file))
        self.assertEqual(run.returncode, 0, run.stderr)
        [record] = self.records()
        self.assertEqual((record["source"], record["model"]), ("agent", "unknown"))

    def test_record_stops_in_a_repository_with_the_record_hook(self) -> None:
        # The variables of the harness can be cleared, so the settings of the repository decide.
        nonce = self.render()
        file = self.write("result.txt", result(nonce), folder=self.base)
        for name in (".claude/settings.json", ".codex/hooks.json"):
            with self.subTest(name=name):
                hook = {"hooks": [{"type": "command", "command": "x/.claude/hooks/record-result.sh"}]}
                self.write(name, json.dumps({"hooks": {"SubagentStop": [hook]}}))
                run = self.run_script("record", "review", str(file))
                self.assertEqual(run.returncode, 1)
                self.assertIn("through the SubagentStop hook", run.stderr)
                (self.repo / name).unlink()
        self.assertEqual(self.records(), [])

    def test_record_stops_in_a_worktree_whose_own_settings_have_the_hook(self) -> None:
        tree = self.base / "wt"
        git("worktree", "add", "-q", "-b", "feat", str(tree), cwd=self.repo)
        nonce = self.render(cwd=tree)
        file = self.write("result.txt", result(nonce), folder=self.base)
        hook = {"hooks": [{"type": "command", "command": "x/.claude/hooks/record-result.sh"}]}
        self.write(".claude/settings.local.json", json.dumps({"hooks": {"SubagentStop": [hook]}}), folder=tree)
        run = self.run_script("record", "review", str(file), cwd=tree)
        self.assertEqual(run.returncode, 1)
        self.assertIn("through the SubagentStop hook", run.stderr)
        self.assertEqual(self.records(), [])

    def test_record_stops_with_the_hook_in_a_codex_config_or_in_the_home_folder(self) -> None:
        nonce = self.render()
        file = self.write("result.txt", result(nonce), folder=self.base)
        toml = '[[hooks.SubagentStop]]\n[[hooks.SubagentStop.hooks]]\ntype = "command"\n' \
               'command = "x/.codex/hooks/record-result.sh"\n'
        hook = json.dumps({"hooks": {"SubagentStop": [{"hooks": [{"command": "$CLAUDE_PROJECT_DIR/.claude/hooks/"
                                                                             "record-result.sh"}]}]}})
        codex_home = self.base / "codex-home"
        env = dict(self.env, CODEX_HOME=str(codex_home))
        cases = ((self.repo, ".codex/config.toml", toml), (self.home, ".claude/settings.json", hook),
                 (self.home, ".codex/config.toml", toml), (self.home, ".codex/hooks.json", hook),
                 (codex_home, "hooks.json", hook), (codex_home, "config.toml", toml))
        for folder, name, text in cases:
            with self.subTest(name=f"{folder.name}/{name}"):
                path = self.write(name, text, folder=folder)
                run = self.run_script("record", "review", str(file), env=env)
                self.assertEqual(run.returncode, 1)
                self.assertIn("through the SubagentStop hook", run.stderr)
                path.unlink()
        self.assertEqual(self.records(), [])

    def test_record_in_a_worktree_stops_with_the_hook_in_the_main_checkout(self) -> None:
        tree = self.base / "wt"
        git("worktree", "add", "-q", "-b", "feat", str(tree), cwd=self.repo)
        nonce = self.render(cwd=tree)
        file = self.write("result.txt", result(nonce), folder=self.base)
        self.write(".codex/config.toml", '[[hooks.SubagentStop]]\ncommand = "x/record-result.sh"\n')
        run = self.run_script("record", "review", str(file), cwd=tree)
        self.assertEqual(run.returncode, 1)
        self.assertIn("through the SubagentStop hook", run.stderr)

    def test_record_needs_the_target_of_the_packet(self) -> None:
        nonce = self.render()
        file = self.write("result.txt", result(nonce), folder=self.base)
        run = self.run_script("record", "prose", str(file))
        self.assertEqual(run.returncode, 1)
        self.assertIn("belongs to a packet of review", run.stderr)

    def test_record_stops_in_claude_code(self) -> None:
        nonce = self.render()
        file = self.write("result.txt", result(nonce), folder=self.base)
        run = self.run_script("record", "review", str(file), env=dict(self.env, CLAUDECODE="1"))
        self.assertEqual(run.returncode, 1)
        self.assertIn("the SubagentStop hook writes the record", run.stderr)
        self.assertEqual(self.records(), [])

    def codex_transcript(self, home: Path, parent: str, message: str, name: str = "rollout-1.jsonl",
                         fork: bool = False) -> None:
        meta = {"id": "child", "parent_thread_id": parent, "forked_from_id": parent if fork else None,
                "source": {"subagent": {"thread_spawn": {"parent_thread_id": parent}}}}
        lines = [{"type": "session_meta", "payload": meta}]
        if fork:
            # A forked agent replays the turns of its parent, with the session_meta of the parent.
            lines += [{"type": "session_meta", "payload": {"id": parent}},
                      {"type": "event_msg", "payload": {"type": "task_complete", "last_agent_message": message}}]
        else:
            lines += [{"type": "turn_context", "payload": {"model": "gpt-5.5-codex"}},
                      {"type": "event_msg", "payload": {"type": "task_complete", "last_agent_message": message}}]
        self.write(f"sessions/2026/11/14/{name}", "".join(json.dumps(line) + "\n" for line in lines), folder=home)

    def test_record_in_codex_takes_the_result_from_the_transcript(self) -> None:
        nonce = self.render()
        home = self.base / "codex"
        self.codex_transcript(home, "thread-1", result(nonce, findings='[{summary: s, reason: r}]'))
        # The file of the agent says there are no findings, but the fresh agent said otherwise.
        file = self.write("result.txt", result(nonce), folder=self.base)
        env = dict(self.env, CODEX_THREAD_ID="thread-1", CODEX_HOME=str(home))
        run = self.run_script("record", "review", str(file), env=env)
        self.assertEqual(run.returncode, 0, run.stderr)
        [record] = self.records()
        self.assertEqual(record["model"], "gpt-5.5-codex")
        self.assertEqual(record["findings"], [{"summary": "s", "reason": "r"}])

    def test_record_in_codex_needs_a_fresh_agent_of_this_thread(self) -> None:
        nonce = self.render()
        home = self.base / "codex"
        self.codex_transcript(home, "another-thread", result(nonce))
        file = self.write("result.txt", result(nonce), folder=self.base)
        env = dict(self.env, CODEX_THREAD_ID="thread-1", CODEX_HOME=str(home))
        run = self.run_script("record", "review", str(file), env=env)
        self.assertEqual(run.returncode, 1)
        self.assertIn("no fresh agent of this Codex thread", run.stderr)
        self.assertEqual(self.records(), [])

    def test_record_in_codex_refuses_a_forked_agent(self) -> None:
        nonce = self.render()
        home = self.base / "codex"
        self.codex_transcript(home, "thread-1", result(nonce), fork=True)
        file = self.write("result.txt", result(nonce), folder=self.base)
        run = self.run_script("record", "review", str(file),
                              env=dict(self.env, CODEX_THREAD_ID="thread-1", CODEX_HOME=str(home)))
        self.assertEqual(run.returncode, 1)
        self.assertIn("no fresh agent of this Codex thread", run.stderr)
        self.assertEqual(self.records(), [])

    def test_record_in_codex_refuses_a_fork_with_one_session_meta(self) -> None:
        nonce = self.render()
        home = self.base / "codex"
        self.codex_transcript(home, "thread-1", result(nonce))
        path = next((home / "sessions").glob("**/*.jsonl"))
        lines = path.read_text().splitlines()
        first = json.loads(lines[0])
        first["payload"]["forked_from_id"] = "thread-1"
        path.write_text("\n".join([json.dumps(first)] + lines[1:]) + "\n")
        file = self.write("result.txt", result(nonce), folder=self.base)
        run = self.run_script("record", "review", str(file),
                              env=dict(self.env, CODEX_THREAD_ID="thread-1", CODEX_HOME=str(home)))
        self.assertEqual(run.returncode, 1)
        self.assertEqual(self.records(), [])

    def test_record_in_codex_needs_the_spawn_parent_of_this_thread(self) -> None:
        nonce = self.render()
        home = self.base / "codex"
        self.codex_transcript(home, "thread-1", result(nonce))
        path = next((home / "sessions").glob("**/*.jsonl"))
        lines = path.read_text().splitlines()
        first = json.loads(lines[0])
        first["payload"]["source"]["subagent"]["thread_spawn"]["parent_thread_id"] = "another-thread"
        path.write_text("\n".join([json.dumps(first)] + lines[1:]) + "\n")
        file = self.write("result.txt", result(nonce), folder=self.base)
        run = self.run_script("record", "review", str(file),
                              env=dict(self.env, CODEX_THREAD_ID="thread-1", CODEX_HOME=str(home)))
        self.assertEqual(run.returncode, 1)
        self.assertEqual(self.records(), [])

    def test_a_date_in_the_findings_is_kept_as_text(self) -> None:
        nonce = self.render()
        text = result(nonce, findings="[{summary: s, reason: r, when: 2026-11-14}]")
        run = self.hook({"last_assistant_message": text})
        self.assertIn("record: wrote", run.stderr)
        [record] = self.records()
        self.assertEqual(record["findings"][0]["when"], "2026-11-14")
        self.assertEqual([p.name for p in (self.repo / ".agents/log/records").iterdir()], [f"{nonce}.json"])

    def test_record_in_codex_needs_the_nonce_in_the_transcript(self) -> None:
        nonce, other = self.render(), self.render()
        home = self.base / "codex"
        self.codex_transcript(home, "thread-1", result(other))
        file = self.write("result.txt", result(nonce), folder=self.base)
        run = self.run_script("record", "review", str(file),
                              env=dict(self.env, CODEX_THREAD_ID="thread-1", CODEX_HOME=str(home)))
        self.assertEqual(run.returncode, 1)
        self.assertIn("no fresh agent of this Codex thread", run.stderr)
        self.assertEqual(self.records(), [])

    def test_skip_lets_one_tree_through(self) -> None:
        run = self.run_script("skip", "review", "a", "typo")
        self.assertEqual(run.returncode, 0, run.stderr)
        [record] = self.records()
        gate = load("commit_gate")
        self.assertEqual((record["source"], record["reason"]), ("skip", "a typo"))
        self.assertTrue(gate.record_counts(record))
        self.assertEqual(gate.missing_targets(["review"], self.records(), gate.worktree_tree(self.repo)), [])

    def test_skip_needs_a_target_and_a_reason(self) -> None:
        self.assertIn("is not an agentic target", self.run_script("skip", "lint", "x").stderr)
        self.assertEqual(self.run_script("skip", "review", " ").returncode, 1)
        self.assertEqual(self.run_script("skip", "review").returncode, 2)
        self.assertEqual(self.records(), [])

    def test_a_linked_records_folder_gets_no_write(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        (self.repo / ".agents/log").mkdir(parents=True)
        (self.repo / ".agents/log/records").symlink_to(outside)
        run = self.run_script("skip", "review", "typo")
        self.assertEqual(run.returncode, 1)
        self.assertIn("is a link", run.stderr)
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
