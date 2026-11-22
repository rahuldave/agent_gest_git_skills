"""Check the records of the agentic targets: `record_result.py hook`, `record` and `skip`, in scratch repositories.

The tests need pyyaml, as the recipes do: `uv run --no-project --with pyyaml python -m unittest
scripts/test_record_result.py`.
"""

from __future__ import annotations

import contextlib
import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".agents/skills/gcm/scripts"
SCRIPT = SCRIPTS / "record_result.py"
HARNESS = ("CLAUDE_CODE_SESSION_ID", "CLAUDECODE", "CODEX_THREAD_ID", "CODEX_HOME")
# The transcripts of the three fresh agents whose results got no record in a Gossil session on 2026-11-22, and the
# packets of their nonces. Each transcript keeps its line count, its first prompt, its model and its SubagentHandback
# call as saved, with the paths of the person replaced. Each other line is a stub, since the saved lines hold the
# prompts and settings of the person.
FIXTURES = ROOT / "fixtures/record_hook"


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
        # The hook waits for a handback in the transcript. Most tests need no wait.
        self.env.update(RECORD_HOOK_WAIT_SECONDS="0", RECORD_HOOK_POLL_SECONDS="0.05")
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

    def test_the_trees_of_a_packet_and_a_record_stay_for_the_scopes_of_the_gate(self) -> None:
        # A change of a page alone keeps the review. The gate needs the tree of the record for that, and the packet
        # and the record keep their trees in the folder objects of the shared log folder.
        nonce = self.render()
        run = self.hook({"last_assistant_message": result(nonce)})
        self.assertEqual(run.returncode, 0, run.stderr)
        [record] = self.records()
        self.assertTrue((self.repo / ".agents/log/objects").is_dir())
        self.write("docs/guide.md", "a page\n")
        gate = load("commit_gate")
        tree = gate.worktree_tree(self.repo)
        self.assertNotEqual(tree, record["output_tree"])
        # The gate compares with the commit tree, which git commit writes to .git/objects.
        git("add", "-A", cwd=self.repo, env=self.env)
        self.assertEqual(git("write-tree", cwd=self.repo, env=self.env).strip(), tree)
        self.assertEqual(gate.missing_targets(["review"], self.records(), tree, self.repo), [])
        self.write("a.txt", "code\n")
        git("add", "-A", cwd=self.repo, env=self.env)
        tree = git("write-tree", cwd=self.repo, env=self.env).strip()
        self.assertEqual(gate.missing_targets(["review"], self.records(), tree, self.repo), ["review"])

    def test_a_kept_tree_that_does_not_hash_to_its_name_is_kept_again(self) -> None:
        agentic = load("agentic_target")
        tree = agentic.worktree_diff(self.repo, keep=True)[1]
        kept = self.repo / ".agents/log/objects" / tree
        kept.chmod(0o644)
        kept.write_bytes(b"forged")
        self.assertEqual(agentic.worktree_diff(self.repo, keep=True)[1], tree)
        self.assertNotEqual(kept.read_bytes(), b"forged")
        gate = load("commit_gate")
        objects = gate.Objects(self.repo)
        try:
            self.assertIsNotNone(objects.entries(tree))
        finally:
            objects.close()

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

    def stop_entry(self, agent: str) -> dict:
        return json.loads((self.repo / f".agents/log/hook-stops/{agent}.json").read_text())

    def text_entry(self, text: str = "Working.") -> str:
        return json.dumps({"message": {"model": "claude-opus-5-5", "content": [{"type": "text", "text": text}]}}) + "\n"

    def prompt_entry(self, nonce: str, target: str = "review") -> str:
        """The first prompt of a fresh agent, in the form of the saved transcripts: it names the packet and nonce."""
        text = (f"You are a fresh agent. Your task is one AGENT_TASK v1 packet (target: {target}, nonce: {nonce}). "
                f"Read the packet file first.")
        return json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n"

    def fresh_transcript(self, nonce: str, *lines: str) -> Path:
        transcript = self.base / "agent.jsonl"
        transcript.write_text(self.prompt_entry(nonce) + "".join(lines))
        return transcript

    def test_a_stop_with_no_handback_writes_a_hook_stop_and_no_record(self) -> None:
        transcript = self.fresh_transcript(self.render(), self.text_entry())
        self.env.update(RECORD_HOOK_WAIT_SECONDS="0.3")
        run = self.hook({"agent_id": "a1", "last_assistant_message": "", "agent_transcript_path": str(transcript)})
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.records(), [])
        entry = self.stop_entry("a1")
        self.assertEqual((entry["agent_id"], entry["last_assistant_message"], entry["agent_transcript_path"],
                          entry["handback_found"]), ("a1", False, True, False))
        self.assertEqual(entry["transcript"], {"readable": True, "bytes": transcript.stat().st_size, "lines": 2})
        self.assertGreater(entry["rereads"], 0)
        self.assertIn("time", entry)
        [line] = run.stderr.splitlines()
        self.assertIn("no AGENT_RESULT block in the stop of agent a1", line)

    def test_a_prompt_that_holds_the_whole_packet_counts(self) -> None:
        run = subprocess.run([sys.executable, SCRIPTS / "agentic_target.py", "render", "review"], cwd=self.repo,
                             capture_output=True, text=True, env=self.env)
        self.assertEqual(run.returncode, 0, run.stderr)
        transcript = self.base / "agent.jsonl"
        parts = [{"type": "text", "text": run.stdout}]
        transcript.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": parts}}) + "\n")
        self.hook({"agent_id": "a2", "last_assistant_message": "", "agent_transcript_path": str(transcript)})
        self.assertEqual(self.stop_entry("a2")["handback_found"], False)

    def test_each_shape_of_a_fresh_agent_prompt_counts(self) -> None:
        run = subprocess.run([sys.executable, SCRIPTS / "agentic_target.py", "render", "review"], cwd=self.repo,
                             capture_output=True, text=True, env=self.env)
        self.assertEqual(run.returncode, 0, run.stderr)
        nonce = next(line.split(":", 1)[1].strip() for line in run.stdout.splitlines() if line.startswith("nonce:"))
        packet = self.write("review.packet", run.stdout, folder=self.base)
        prompts = {"file": f"Read the whole packet in {packet}; then do it.",
                   "sentence": f"Give the top-level nonce from the packet: {nonce} in your result.",
                   "parts": [{"type": "text", "text": "First part."}, {"type": "text", "text": f"nonce: {nonce}"}]}
        for name, content in prompts.items():
            with self.subTest(prompt=name):
                transcript = self.base / f"{name}.jsonl"
                transcript.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": content}})
                                      + "\n")
                self.hook({"agent_id": f"p-{name}", "agent_transcript_path": str(transcript)})
                self.assertEqual(self.stop_entry(f"p-{name}")["handback_found"], False)

    def test_folders_in_the_prompt_do_not_use_up_the_files_to_read(self) -> None:
        module = load("record_result")
        nonce = "c" * 32
        packet = self.write("p.packet", f"<<<AGENT_TASK v1>>>\nnonce: {nonce}\n", folder=self.base)
        folders = " ".join(str(self.base / f"d{i}") for i in range(12))
        self.assertEqual(module.prompt_nonces(f"Work in {folders}. Read {packet}."), {nonce})
        home = self.base / "home"
        self.write("x.packet", f"<<<AGENT_TASK v1>>>\nnonce: {nonce}\n", folder=home)
        with unittest.mock.patch.dict(os.environ, {"HOME": str(home)}):
            self.assertEqual(module.prompt_nonces("Read ~/x.packet first."), {nonce})

    def test_a_pipe_named_in_the_prompt_is_not_read(self) -> None:
        pipe = self.base / "pipe"
        os.mkfifo(pipe)
        transcript = self.base / "agent.jsonl"
        transcript.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": f"Read {pipe}."}})
                              + "\n")
        run = subprocess.run([sys.executable, SCRIPT, "hook"], cwd=self.repo, env=self.env, capture_output=True,
                             timeout=20, input=json.dumps({"agent_transcript_path": str(transcript),
                                                          "cwd": str(self.repo)}).encode())
        self.assertEqual((run.returncode, run.stderr), (0, b""))

    def test_an_ordinary_subagent_returns_at_once_and_silently(self) -> None:
        nonce = self.render()
        ordinary = self.base / "explore.jsonl"
        ordinary.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": "Find the tests."}})
                            + "\n" + self.text_entry("Here they are."))
        unknown = self.base / "unknown.jsonl"
        unknown.write_text(self.prompt_entry("b" * 32))  # A packet nonce with no packet file.
        quoted = self.base / "quoted.jsonl"
        # Only the first prompt counts, so a packet that a later message names does not make a fresh agent.
        quoted.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": "Look around."}}) + "\n"
                          + self.prompt_entry(nonce))
        self.env.update(RECORD_HOOK_WAIT_SECONDS="5")
        for event in ({"agent_id": "o1", "last_assistant_message": "Here they are.",
                       "agent_transcript_path": str(ordinary)},
                      {"agent_id": "o3", "agent_transcript_path": str(unknown)},
                      {"agent_id": "o4", "agent_transcript_path": str(quoted)},
                      {"agent_id": "o5", "agent_transcript_path": str(self.base / "missing.jsonl")},
                      {"agent_id": "o6", "agent_transcript_path": str(ordinary), "cwd": str(self.base)},
                      {"agent_id": "o7", "last_assistant_message": "hi", "agent_transcript_path": str(ordinary),
                       "cwd": str(self.base / "gone")}):
            with self.subTest(agent=event["agent_id"]):
                start = time.monotonic()
                run = self.hook(event)
                self.assertLess(time.monotonic() - start, 2.5)
                self.assertEqual((run.returncode, run.stderr), (0, ""))
        self.assertFalse((self.repo / ".agents/log/hook-stops").exists())

    def test_a_stop_with_no_transcript_path_writes_a_hook_stop_with_no_wait(self) -> None:
        self.env.update(RECORD_HOOK_WAIT_SECONDS="5")
        start = time.monotonic()
        run = self.hook({"agent_id": "n1", "last_assistant_message": "Done."})
        self.assertLess(time.monotonic() - start, 2.5)
        self.assertEqual(run.returncode, 0, run.stderr)
        entry = self.stop_entry("n1")
        self.assertEqual((entry["last_assistant_message"], entry["agent_transcript_path"], entry["transcript"],
                          entry["handback_found"], entry["rereads"]), (True, False, None, False, 0))
        [line] = run.stderr.splitlines()
        self.assertIn("transcript path: no", line)
        module = load("record_result")
        with unittest.mock.patch.object(module, "write_record", side_effect=module.Stop("two\nlines")), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(module.hook(json.dumps({"agent_id": "n3", "cwd": str(self.repo)}).encode()), 0)
        self.assertEqual(len(err.getvalue().splitlines()), 1)
        # Outside a repository the file cannot be written, and the one line says why.
        run = self.hook({"agent_id": "n2"}, cwd=self.base)
        self.assertEqual(run.returncode, 0, run.stderr)
        [line] = run.stderr.splitlines()
        self.assertIn("no hook-stops file", line)

    def test_a_handback_with_no_block_stops_the_wait(self) -> None:
        call = {"type": "tool_use", "name": "SubagentHandback", "input": {"message": "No result here."}}
        transcript = self.fresh_transcript(self.render(), json.dumps({"message": {"content": [call]}}) + "\n")
        self.env.update(RECORD_HOOK_WAIT_SECONDS="5")
        start = time.monotonic()
        self.hook({"agent_id": "a4", "agent_transcript_path": str(transcript)})
        self.assertLess(time.monotonic() - start, 4)
        entry = self.stop_entry("a4")
        self.assertEqual((entry["handback_found"], entry["rereads"]), (True, 0))

    def test_an_agent_id_that_is_not_a_plain_name_gives_a_name_of_its_own(self) -> None:
        transcript = self.fresh_transcript(self.render())
        run = self.hook({"agent_id": "../../escape", "agent_transcript_path": str(transcript)})
        self.assertEqual(run.returncode, 0, run.stderr)
        [path] = (self.repo / ".agents/log/hook-stops").iterdir()
        self.assertTrue(path.name.startswith("unknown-"))
        self.assertEqual(json.loads(path.read_text())["agent_id"], "../../escape")
        self.assertFalse((self.base / "escape.json").exists())

    def test_the_hook_waits_for_a_handback_that_comes_late(self) -> None:
        nonce = self.render()
        transcript = self.fresh_transcript(nonce, self.text_entry())
        call = {"type": "tool_use", "name": "SubagentHandback", "input": {"message": result(nonce)}}

        def append() -> None:
            time.sleep(0.5)
            with transcript.open("a") as handle:
                handle.write(json.dumps({"message": {"model": "claude-opus-5-5", "content": [call]}}) + "\n")

        self.env.update(RECORD_HOOK_WAIT_SECONDS="5", RECORD_HOOK_POLL_SECONDS="0.1")
        writer = threading.Thread(target=append)
        writer.start()
        self.addCleanup(writer.join)
        run = self.hook({"agent_id": "a5", "last_assistant_message": "", "agent_transcript_path": str(transcript)})
        writer.join()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("record: wrote", run.stderr)
        [record] = self.records()
        self.assertEqual(record["nonce"], nonce)
        self.assertFalse((self.repo / ".agents/log/hook-stops").exists())

    def test_the_wait_reads_the_transcript_again_until_the_handback_comes(self) -> None:
        module = load("record_result")
        transcript = self.base / "agent.jsonl"
        transcript.write_text(self.text_entry())
        call = {"type": "tool_use", "name": "SubagentHandback", "input": {"message": result("b" * 32)}}
        reads = []
        real = module.handback_message

        def handback(path):
            reads.append(path)
            if len(reads) == 3:  # Claude Code writes the handback after the hook read the transcript twice.
                with transcript.open("a") as handle:
                    handle.write(json.dumps({"message": {"content": [call]}}) + "\n")
            return real(path)

        with unittest.mock.patch.dict(os.environ, {"RECORD_HOOK_WAIT_SECONDS": "5", "RECORD_HOOK_POLL_SECONDS": "0.01"}), \
                unittest.mock.patch.object(module, "handback_message", handback):
            message, found, rereads = module.find_message({"last_assistant_message": ""}, str(transcript))
        self.assertEqual((module.has_block(message), found, rereads), (True, True, 2))

    def test_input_nested_too_deep_never_stops_the_agent(self) -> None:
        run = self.run_script("hook", stdin="[" * 100000)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn("Traceback", run.stderr)

    def test_a_block_in_the_first_read_adds_no_delay(self) -> None:
        module = load("record_result")
        transcript = self.base / "agent.jsonl"
        call = {"type": "tool_use", "name": "SubagentHandback", "input": {"message": result("b" * 32)}}
        transcript.write_text(json.dumps({"message": {"content": [call]}}) + "\n")
        with unittest.mock.patch.dict(os.environ, {"RECORD_HOOK_WAIT_SECONDS": "5"}), \
                unittest.mock.patch.object(module.time, "sleep", side_effect=AssertionError("slept")):
            for event in ({"last_assistant_message": result("b" * 32)}, {"last_assistant_message": ""}):
                message, _, rereads = module.find_message(event, str(transcript))
                self.assertEqual((module.has_block(message), rereads), (True, 0))

    def test_the_wait_settings_ignore_values_that_are_not_numbers(self) -> None:
        module = load("record_result")
        for value, expected in (("x", 2.0), ("nan", 2.0), ("inf", 2.0), ("-1", 0.0), ("99", 10.0), ("0.5", 0.5)):
            with self.subTest(value=value), unittest.mock.patch.dict(os.environ, {"RECORD_HOOK_WAIT_SECONDS": value}):
                self.assertEqual(module.seconds(module.WAIT_VARIABLE, module.WAIT_SECONDS, 0.0, 10.0), expected)

    def test_the_saved_transcripts_of_the_missed_results(self) -> None:
        packets = self.repo / ".agents/log/packets"
        packets.mkdir(parents=True)
        for packet in sorted((FIXTURES / "packets").glob("*.json")):
            data = json.loads(packet.read_text())
            data["worktree"] = str(self.repo)
            (packets / packet.name).write_text(json.dumps(data))
        saved = sorted(FIXTURES.glob("agent-*.jsonl"))
        self.assertEqual(len(saved), 3)
        for path in saved:
            agent = path.name[len("agent-"):-len(".jsonl")]
            lines = path.read_text().splitlines(keepends=True)
            last = max(i for i, line in enumerate(lines) if '"SubagentHandback"' in line)
            with self.subTest(agent=agent):
                # The transcript before Claude Code wrote the handback: a hook-stops file and no record.
                truncated = self.base / f"{agent}.truncated.jsonl"
                truncated.write_text("".join(lines[:last]))
                before = len(self.records())
                run = self.hook({"agent_id": agent, "last_assistant_message": "",
                                 "agent_transcript_path": str(truncated)})
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(len(self.records()), before)
                entry = self.stop_entry(agent)
                self.assertEqual((entry["handback_found"], entry["transcript"]["lines"]), (False, last))
                # The full transcript writes the record.
                full = self.base / f"{agent}.jsonl"
                full.write_text("".join(lines))
                run = self.hook({"agent_id": agent, "last_assistant_message": "", "agent_transcript_path": str(full)})
                self.assertIn("record: wrote", run.stderr)
                self.assertEqual(len(self.records()), before + 1)
        self.assertEqual(sorted(record["nonce"] for record in self.records()),
                         sorted(packet.stem for packet in (FIXTURES / "packets").glob("*.json")))

    def test_a_hook_stop_that_cannot_be_written_never_stops_the_agent(self) -> None:
        transcript = str(self.fresh_transcript(self.render()))
        log = self.repo / ".agents/log"
        (log / "hook-stops").write_text("a file, not a folder\n")
        run = self.hook({"agent_id": "a6", "agent_transcript_path": transcript})
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("no hook-stops file", run.stderr)
        self.assertNotIn("Traceback", run.stderr)
        (log / "hook-stops").unlink()
        log.chmod(0o500)
        self.addCleanup(log.chmod, 0o755)
        run = self.hook({"agent_id": "a7", "agent_transcript_path": transcript})
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("no hook-stops file", run.stderr)
        log.chmod(0o755)
        module = load("record_result")
        event = json.dumps({"agent_id": "a9", "cwd": str(self.repo), "agent_transcript_path": transcript}).encode()
        with unittest.mock.patch.object(module, "write_record", side_effect=RuntimeError("boom")), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(module.hook(event), 0)
        self.assertIn("no hook-stops file: boom", err.getvalue())
        with unittest.mock.patch.object(module, "transcript_size", side_effect=RuntimeError("boom")), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(module.hook(event), 0)
        self.assertIn("no hook-stops file", err.getvalue())

    def test_only_input_that_is_not_json_returns_at_once(self) -> None:
        module = load("record_result")
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(module.hook(b"not json"), 0)
        self.assertIn("is not JSON", err.getvalue())
        # A ValueError after the input was read is a fault of the hook, and the hook says so.
        with unittest.mock.patch.object(module, "find_message", side_effect=ValueError("late")), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(module.hook(json.dumps({"cwd": str(self.repo)}).encode()), 0)
        self.assertIn("no record of this result: ValueError('late')", err.getvalue())

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

    def refusal(self, nonce: str) -> dict:
        return json.loads((self.repo / f".agents/log/refusals/{nonce}.json").read_text())

    def test_a_result_without_follow_up_leaves_a_refusal_that_the_gate_names(self) -> None:
        nonce = self.render()
        run = self.hook({"last_assistant_message": result(nonce).replace("follow_up: []\n", "")})
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.records(), [])
        refusal = self.refusal(nonce)
        self.assertEqual((refusal["nonce"], refusal["target"]), (nonce, "review"))
        self.assertIn("missing follow_up", refusal["reason"])
        gate = load("commit_gate")
        tree = gate.worktree_tree(self.repo)
        folders = gate.log_folders(self.repo)
        # The refusal does not count as a record.
        self.assertEqual(gate.missing_targets(["review"], gate.load_records(folders), tree), ["review"])
        [note] = gate.refusal_notes(folders, ["review"], tree, self.repo)
        self.assertIn(nonce, note)
        self.assertIn("missing follow_up", note)
        self.assertIn("`just review`", note)

    def test_the_gate_says_which_nonce_was_refused_and_why(self) -> None:
        nonce = self.render()
        self.hook({"last_assistant_message": result(nonce).replace("follow_up: []\n", "")})
        gate = load("commit_gate")
        env = dict(self.env, CLAUDE_CODE_SESSION_ID="s")
        tree = gate.worktree_tree(self.repo)
        with unittest.mock.patch.dict(os.environ, env, clear=True), \
                unittest.mock.patch.object(gate, "commit_tree", return_value=tree), \
                unittest.mock.patch.object(gate, "read_at", side_effect=lambda root, rev, path:
                                           '{"steps": []}' if path == gate.STACK else None), \
                unittest.mock.patch.object(gate, "parents_of_commit", return_value=[]), \
                unittest.mock.patch.object(gate, "recipes", return_value={"check", "review"}), \
                unittest.mock.patch.object(gate, "has_pass", return_value=True), \
                unittest.mock.patch.object(gate, "required_against", return_value=["review"]):
            with self.assertRaises(gate.Stop) as stopped:
                gate.gate(self.repo)
        message = str(stopped.exception)
        self.assertIn("no record for this tree of `just review`", message)
        self.assertIn(f"refused the result of `just review` with the nonce {nonce}", message)
        self.assertIn("missing follow_up", message)

    def test_a_valid_result_after_a_refusal_records_and_the_gate_passes(self) -> None:
        nonce = self.render()
        self.hook({"last_assistant_message": result(nonce).replace("follow_up: []\n", "")})
        run = self.hook({"last_assistant_message": result(nonce)})
        self.assertIn("record: wrote", run.stderr)
        [record] = self.records()
        gate = load("commit_gate")
        tree = gate.worktree_tree(self.repo)
        folders = gate.log_folders(self.repo)
        self.assertEqual(gate.missing_targets(["review"], gate.load_records(folders), tree), [])
        # The packet has its record, so the old refusal is no reason any more.
        self.assertEqual(gate.refusal_notes(folders, ["review"], tree, self.repo), [])

    def test_a_refusal_of_an_old_tree_is_not_named(self) -> None:
        nonce = self.render()
        self.hook({"last_assistant_message": result(nonce).replace("follow_up: []\n", "")})
        self.write("a.txt", "c\n")
        gate = load("commit_gate")
        tree = gate.worktree_tree(self.repo)
        self.assertEqual(gate.refusal_notes(gate.log_folders(self.repo), ["review"], tree, self.repo), [])

    def packet_text(self, target: str = "review") -> str:
        run = subprocess.run([sys.executable, SCRIPTS / "agentic_target.py", "render", target], cwd=self.repo,
                             capture_output=True, text=True, env=self.env)
        self.assertEqual(run.returncode, 0, run.stderr)
        return run.stdout

    def test_a_result_after_a_quote_of_the_packet_records(self) -> None:
        # The form of the result in the packet is indented, so it is no second block.
        packet = self.packet_text()
        nonce = next(line.split(":", 1)[1].strip() for line in packet.splitlines() if line.startswith("nonce:"))
        run = self.hook({"last_assistant_message": packet + "\n" + result(nonce)})
        self.assertIn("record: wrote", run.stderr)
        self.assertEqual(len(self.records()), 1)
        self.assertFalse((self.repo / f".agents/log/refusals/{nonce}.json").exists())

    def test_a_quote_of_the_packet_alone_leaves_no_refusal(self) -> None:
        packet = self.packet_text()
        run = self.hook({"last_assistant_message": "Here is the task.\n" + packet})
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.records(), [])
        self.assertFalse((self.repo / ".agents/log/refusals").exists())

    def test_a_newer_record_of_the_target_makes_a_refusal_old(self) -> None:
        refused = self.render()
        self.hook({"last_assistant_message": result(refused).replace("follow_up: []\n", "")})
        gate = load("commit_gate")
        tree = gate.worktree_tree(self.repo)
        folders = gate.log_folders(self.repo)
        os.utime(self.repo / f".agents/log/refusals/{refused}.json", (1, 1))
        # A later run of the target gave a record with an open finding: that is the news, not the refusal.
        nonce = self.render()
        self.hook({"last_assistant_message": result(nonce, status="partial", findings="[{summary: s}]")})
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(gate.refusal_notes(folders, ["review"], tree, self.repo), [])

    def test_a_newer_record_of_another_tree_keeps_the_refusal(self) -> None:
        # A record of the same target from another worktree, for its own tree, is no news about this refusal.
        refused = self.render()
        self.hook({"last_assistant_message": result(refused).replace("follow_up: []\n", "")})
        os.utime(self.repo / f".agents/log/refusals/{refused}.json", (1, 1))
        gate = load("commit_gate")
        tree = gate.worktree_tree(self.repo)
        other = {"version": 1, "target": "review", "status": "success", "input_tree": "c" * 40,
                 "output_tree": "c" * 40, "findings": [], "source": "skip", "reason": "r"}
        (self.repo / ".agents/log/records").mkdir()
        (self.repo / ".agents/log/records/other.json").write_text(json.dumps(other))
        (self.repo / ".agents/log/records/junk.json").write_text(json.dumps({"target": "review"}))
        [note] = gate.refusal_notes(gate.log_folders(self.repo), ["review"], tree, self.repo)
        self.assertIn(refused, note)

    def test_a_newer_changer_record_of_this_worktree_makes_an_old_tree_refusal_old(self) -> None:
        self.write(".agents/skills/gdo/references/targets/update-docs.md", "DOCS TASK\n")
        docs = lambda nonce: result(nonce, target="update-docs").replace("  findings: []", "  files: []\n  checked: []")
        refused = self.render("update-docs")
        self.hook({"last_assistant_message": docs(refused).replace("follow_up: []\n", "")})
        os.utime(self.repo / f".agents/log/refusals/{refused}.json", (1, 1))
        self.write("a.txt", "c\n")
        gate = load("commit_gate")
        folders = gate.log_folders(self.repo)
        # The tree moved, and the refusal of this worktree is still the reason.
        tree = gate.worktree_tree(self.repo)
        [note] = gate.refusal_notes(folders, ["update-docs"], tree, self.repo)
        self.assertIn(refused, note)
        # A later update-docs of this worktree worked, then the tree moved again: the old refusal is no reason.
        self.hook({"last_assistant_message": docs(self.render("update-docs"))})
        self.assertEqual(len(self.records()), 1)
        self.write("a.txt", "d\n")
        tree = gate.worktree_tree(self.repo)
        self.assertEqual(gate.refusal_notes(folders, ["update-docs"], tree, self.repo), [])

    def test_a_bad_refusal_file_never_stops_the_gate_with_a_fault(self) -> None:
        gate = load("commit_gate")
        tree = gate.worktree_tree(self.repo)
        folder = self.repo / ".agents/log/refusals"
        folder.mkdir(parents=True)
        bad = ["[1]", "not json", json.dumps({"version": 1, "target": ["review"], "nonce": "a", "reason": "r"}),
               json.dumps({"version": 1, "target": "prose", "nonce": "a", "reason": "r", "input_tree": "x",
                           "worktree": "/tmp/a\u0000b"}),
               json.dumps({"version": 1, "target": "prose", "nonce": "a", "reason": "r", "input_tree": "x",
                           "worktree": 7})]
        for i, text in enumerate(bad):
            (folder / f"{i}.json").write_text(text)
        self.assertEqual(gate.refusal_notes(gate.log_folders(self.repo), ["review", "prose"], tree, self.repo), [])

    def test_the_gate_drops_the_control_characters_of_a_reason(self) -> None:
        gate = load("commit_gate")
        tree = gate.worktree_tree(self.repo)
        folder = self.repo / ".agents/log/refusals"
        folder.mkdir(parents=True)
        (folder / "n.json").write_text(json.dumps({"version": 1, "target": "review", "nonce": "a" * 32,
                                                   "input_tree": tree, "reason": "bad\x1b]8;;x\x07 \x9b\u202e end"}))
        [note] = gate.refusal_notes(gate.log_folders(self.repo), ["review"], tree, self.repo)
        self.assertTrue(all(c.isprintable() for c in note), note)
        self.assertIn("a" * 32, note)
        self.assertIn("end", note)

    def test_a_result_with_no_packet_leaves_no_refusal(self) -> None:
        self.render()
        self.hook({"last_assistant_message": result("b" * 32).replace("follow_up: []\n", "")})
        folder = self.repo / ".agents/log/refusals"
        self.assertEqual(list(folder.glob("*.json")) if folder.is_dir() else [], [])

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
