"""Check the agentic targets of gcm: the packet that `agentic_target.py render` prints, in scratch repositories."""

from __future__ import annotations

import errno
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/gcm/scripts/agentic_target.py"
_spec = importlib.util.spec_from_file_location("agentic_target", SCRIPT)
agentic_target = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agentic_target)
# The line that installs the release binary of jagt, for the hints.
JAGT_LINE = "curl -fsSL https://raw.githubusercontent.com/rahuldave/jagt/7ea80a99492fe5eed5d7fa9b9a4e1ba08599463a/scripts/install.sh | sh -s -- --tag v0.6.3"


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


class RequiredJagtTests(unittest.TestCase):
    """Before jagt 0.6.3, jagt can save the review packet where commit_gate.py does not read it, in a submodule or a
    linked worktree. So the package requires jagt 0.6.3 or later."""

    def test_the_package_requires_jagt_0_6_3_with_a_local_check(self) -> None:
        required = json.loads((ROOT / "skill-package.json").read_text())["executables"]["required"]
        jagt = next((entry for entry in required if entry["name"] == "jagt"), None)
        self.assertIsNotNone(jagt, "skill-package.json does not require jagt")
        self.assertEqual(jagt["version"], ">=0.6.3")
        # The check runs the installed program alone. A check through cargo, uvx, npx or curl could download it.
        self.assertEqual(jagt["check"], "jagt --version")
        # The release binary first, the build from source second.
        self.assertTrue(jagt["install"].startswith(f"Run `{JAGT_LINE}`, "), jagt["install"])
        # The command ends at a backtick, so a copy of it never takes the comma of the sentence.
        self.assertIn(f"`{JAGT_LINE}`", agentic_target.JAGT_INSTALL)
        self.assertIn("build it from source", jagt["install"])
        self.assertIn(JAGT_LINE, agentic_target.JAGT_INSTALL)
        self.assertLess(agentic_target.JAGT_INSTALL.index(JAGT_LINE), agentic_target.JAGT_INSTALL.index("from source"))

    @unittest.skipUnless(shutil.which("jagt"), "needs jagt")
    def test_the_check_prints_a_version_that_meets_the_floor(self) -> None:
        printed = subprocess.run(["jagt", "--version"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(printed.returncode, 0, printed.stderr)
        version = printed.stdout.split()[-1]
        self.assertGreaterEqual(tuple(int(part) for part in version.split(".")[:3]), (0, 6, 3), printed.stdout)


class RequiredGestTests(unittest.TestCase):
    """The tasker role needs the gest of the fork of rahuldave, 0.6.0 or later. Its gest --version prints the marker
    (rahuldave), and the gest of crates.io does not, so the check of the manifest refuses that gest."""

    def setUp(self) -> None:
        required = json.loads((ROOT / "skill-package.json").read_text())["executables"]["required"]
        self.gest = next(entry for entry in required if entry["name"] == "gest")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def fake(self, printed: str) -> Path:
        """A folder with a fake gest that prints printed for gest --version."""
        folder = Path(tempfile.mkdtemp(dir=self.tmp.name))
        (folder / "gest").write_text(f"#!/bin/sh\necho '{printed}'\n")
        (folder / "gest").chmod(0o755)
        return folder

    def passes(self, folder: Path) -> bool:
        """The rule of tools-check of jnterfaces: the check exits 0, its output holds expect, and the first version in
        the output meets the floor."""
        run = subprocess.run(shlex.split(self.gest["check"]), capture_output=True, text=True,
                             env={**os.environ, "PATH": str(folder)})
        found = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", run.stdout)
        floor = tuple(int(part) for part in self.gest["version"].removeprefix(">=").split("."))
        return (run.returncode == 0 and self.gest["expect"] in run.stdout and found is not None
                and tuple(int(part) for part in found.groups()) >= floor)

    def test_the_package_requires_the_fork_at_0_6_0(self) -> None:
        self.assertEqual(self.gest["check"], "gest --version")
        self.assertEqual(self.gest["version"], ">=0.6.0")
        self.assertEqual(self.gest["expect"], "(rahuldave)")
        line = "curl -fsSL https://raw.githubusercontent.com/rahuldave/gest/v0.6.0/scripts/install.sh | sh -s -- --tag v0.6.0"
        self.assertTrue(self.gest["install"].startswith(f"Run `{line}`, "), self.gest["install"])
        self.assertLess(self.gest["install"].index(line), self.gest["install"].index("from source"))

    def test_a_gest_without_the_marker_fails_and_the_fork_passes(self) -> None:
        self.assertFalse(self.passes(self.fake("gest 0.6.0")))
        self.assertFalse(self.passes(self.fake("gest 0.6.0 (macos-aarch64, 2026-11-17, revision 528a440)")))
        self.assertFalse(self.passes(self.fake("gest 0.5.6 (rahuldave)")))
        self.assertTrue(self.passes(self.fake("gest 0.6.0 (rahuldave)")))

    def test_the_tools_check_of_jnterfaces_agrees(self) -> None:
        # The real check, when a clone of jnterfaces has it. The clone that CI pins may be older and lack it.
        found = subprocess.run([str(ROOT / "scripts/find_jnterfaces.sh"), ".agents/tools_check.py"],
                               capture_output=True, text=True)
        if found.returncode != 0:
            self.skipTest(f"needs .agents/tools_check.py in a clone of jnterfaces: {found.stderr.strip()}")
        script = Path(found.stdout.strip()) / ".agents/tools_check.py"
        manifest = Path(self.tmp.name) / "skill-package.json"
        manifest.write_text(json.dumps({"repository": {"name": "agent_gest_git_skills"},
                                        "executables": {"required": [self.gest]}}))
        for printed, code in (("gest 0.6.0", 1), ("gest 0.6.0 (rahuldave)", 0)):
            with self.subTest(printed=printed):
                run = subprocess.run([sys.executable, str(script), "--manifest", str(manifest)], capture_output=True,
                                     text=True, env={**os.environ, "PATH": f"{self.fake(printed)}{os.pathsep}/usr/bin:/bin"})
                self.assertEqual(run.returncode, code, run.stdout + run.stderr)


@unittest.skipUnless(shutil.which("jagt"), "needs jagt")
class RenderTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="agentic-target-test-")
        self.addCleanup(scratch.cleanup)
        self.base = Path(scratch.name).resolve()
        self.repo = self.base / "proj"
        self.repo.mkdir()
        git("init", "-q", "-b", "main", cwd=self.repo)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
                        GIT_COMMITTER_EMAIL="t@example.com")
        self.write(".agents/skills/grv/references/targets/review.md", "BASE TASK\n")
        self.write(".agents/stack.json", json.dumps({"code": {"python": ["**/*.py"], "rust": ["**/*.rs"]}}))
        self.write(".gitignore", ".agents/log/\n")

    def write(self, path: str, text: str) -> None:
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def render(self, *args: str, cwd=None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, SCRIPT, "render", *args], cwd=cwd or self.repo, capture_output=True,
                              text=True, env=self.env)

    def commit(self) -> None:
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, env=self.env)
        subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=self.repo, check=True, env=self.env)

    def nonce(self, packet: str) -> str:
        return next(line.split(":", 1)[1].strip() for line in packet.splitlines() if line.startswith("nonce:"))

    def test_the_prompt_has_the_layers_in_order(self) -> None:
        self.write(".agents/targets/rust/review.md", "RUST LAYER\n")
        self.write(".agents/targets/python/review.md", "PYTHON LAYER\n")
        self.write(".agents/targets/review.md", "REPOSITORY TEXT\n")
        result = self.render("review")
        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout
        order = [out.index(text) for text in ("BASE TASK", "PYTHON LAYER", "RUST LAYER", "REPOSITORY TEXT")]
        self.assertEqual(order, sorted(order))
        self.assertIn("- findings", out)
        self.assertIn("The layers of the prompt: .agents/skills/grv/references/targets/review.md, "
                      ".agents/targets/python/review.md", result.stderr)

    def test_the_prompt_shows_the_form_of_the_result_with_follow_up(self) -> None:
        # jagt result lint refuses a result with no follow_up, so each packet names the field and shows its form.
        for target in agentic_target.TARGETS:
            with self.subTest(target=target):
                if target != "review":
                    self.write(f".agents/skills/s{target}/references/targets/{target}.md", "BASE TASK\n")
                result = self.render(target)
                self.assertEqual(result.returncode, 0, result.stderr)
                packet = result.stdout
                self.assertIn("follow_up", packet)
                self.assertIn("`follow_up` is a list", packet)
                # The form in the prompt, with the nonce of the packet, is a result that jagt accepts.
                lines = packet.splitlines()
                start = next(i for i, line in enumerate(lines) if line.strip() == "<<<AGENT_RESULT v1>>>")
                end = next(i for i, line in enumerate(lines) if line.strip() == "<<<END_AGENT_RESULT>>>")
                block = "\n".join(line[6:] for line in lines[start:end + 1]) + "\n"
                block = block.replace("<the nonce of this packet>", self.nonce(packet))
                lint = subprocess.run(["jagt", "result", "lint", "--expect-count", "1", "--expect-target", target,
                                       "--expect-nonce", self.nonce(packet), "-"], input=block, capture_output=True,
                                      text=True)
                self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr + block)
                for output in agentic_target.TARGETS[target]:
                    self.assertIn(f"  {output}: []", block)
                # Without follow_up, the same block is refused.
                refused = subprocess.run(["jagt", "result", "lint", "-"], input=block.replace("follow_up: []\n", ""),
                                         capture_output=True, text=True)
                self.assertNotEqual(refused.returncode, 0)

    def test_a_missing_layer_is_left_out(self) -> None:
        result = self.render("review")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("BASE TASK", result.stdout)
        self.assertIn("The layers of the prompt: .agents/skills/grv/references/targets/review.md\n", result.stderr)

    def test_the_diff_holds_untracked_files_and_the_real_index_stays(self) -> None:
        self.write("a.py", "x = 1\n")
        self.commit()
        index = (self.repo / ".git/index").read_bytes()
        self.write("a.py", "x = 2\n")
        self.write("new.py", "y = 1\n")
        result = self.render("review")
        self.assertEqual(result.returncode, 0, result.stderr)
        packet = json.loads((self.repo / f".agents/log/packets/{self.nonce(result.stdout)}.json").read_text())
        head = git("rev-parse", "HEAD", cwd=self.repo).strip()
        diff = (self.repo / f".agents/log/diffs/{head}-{packet['input_tree']}.diff").read_text()
        self.assertIn("-x = 1\n+x = 2", diff)
        self.assertIn("+y = 1", diff)
        self.assertIn(f".agents/log/diffs/{head}-{packet['input_tree']}.diff", result.stdout)
        self.assertNotIn("jagt saved the input tree", result.stderr)
        self.assertEqual((self.repo / ".git/index").read_bytes(), index)
        self.assertEqual(git("status", "--porcelain", cwd=self.repo).split(), ["M", "a.py", "??", "new.py"])

    def test_a_repository_with_no_commit_gets_the_whole_tree_as_the_diff(self) -> None:
        self.write("a.py", "x = 1\n")
        result = self.render("review")
        self.assertEqual(result.returncode, 0, result.stderr)
        diffs = list((self.repo / ".agents/log/diffs").glob("none-*.diff"))
        self.assertEqual(len(diffs), 1)
        self.assertIn("+x = 1", diffs[0].read_text())

    def test_the_arguments_go_into_the_packet(self) -> None:
        self.write(".agents/skills/gdo/references/targets/update-docs.md", "DOCS TASK\n")
        result = self.render("update-docs", "api", "two words")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("argv:\n  - api\n  - two words\n", result.stdout)
        self.assertIn("- files", result.stdout)

    def test_a_linked_worktree_uses_the_shared_log_folder(self) -> None:
        self.commit()
        other = self.base / "other"
        git("worktree", "add", "-q", "-b", "side", str(other), cwd=self.repo)
        result = self.render("review", cwd=other)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(list((self.repo / ".agents/log/diffs").glob("*.diff"))), 1)
        self.assertFalse((other / ".agents/log/diffs").exists())

    def diff_of(self, result: subprocess.CompletedProcess) -> bytes:
        packet = json.loads((self.repo / f".agents/log/packets/{self.nonce(result.stdout)}.json").read_text())
        head = git("rev-parse", "--verify", "--quiet", "HEAD", cwd=self.repo).strip() if (
            self.repo / ".git/refs/heads/main").exists() else "none"
        return (self.repo / f".agents/log/diffs/{head}-{packet['input_tree']}.diff").read_bytes()

    def test_the_diff_keeps_crlf_and_applies(self) -> None:
        (self.repo / "crlf.txt").write_bytes(b"a\r\nb\r\n")
        self.commit()
        (self.repo / "crlf.txt").write_bytes(b"a\r\nc\r\n")
        result = self.render("review")
        self.assertEqual(result.returncode, 0, result.stderr)
        diff = self.diff_of(result)
        self.assertIn(b"-b\r\n+c\r\n", diff)
        patch = self.base / "p.diff"
        patch.write_bytes(diff)
        check = subprocess.run(["git", "apply", "--check", "-R", str(patch)], cwd=self.repo, capture_output=True)
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_a_staged_file_that_gitignore_names_is_in_the_tree_of_the_gate(self) -> None:
        self.write(".gitignore", ".agents/log/\n*.log\n")
        self.commit()
        self.write("force.log", "kept\n")
        git("add", "-f", "force.log", cwd=self.repo)
        spec = importlib.util.spec_from_file_location("commit_gate", ROOT / ".agents/skills/gcm/scripts/commit_gate.py")
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        result = self.render("review")
        self.assertEqual(result.returncode, 0, result.stderr)
        head, tree, diff = self.module().worktree_diff(self.repo)
        self.assertEqual(tree, gate.worktree_tree(self.repo))
        self.assertIn(b"+kept", (self.repo / f".agents/log/diffs/{head}-{tree}.diff").read_bytes())
        # jagt 0.6.0 computes its input tree without the index, so the script warns.
        packet = json.loads((self.repo / f".agents/log/packets/{self.nonce(result.stdout)}.json").read_text())
        if packet["input_tree"] != tree:
            self.assertIn("jagt saved the input tree", result.stderr)

    def test_a_repository_path_with_a_colon_or_a_quote_has_its_tree(self) -> None:
        # Git splits GIT_ALTERNATE_OBJECT_DIRECTORIES at each colon, so the path of the object store goes in quotes.
        repo = self.base / 'we:ird"name'
        repo.mkdir()
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@example.com")
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True, env=env)
        (repo / ".gitignore").write_text("kept.txt\n")
        (repo / "kept.txt").write_text("kept\n")
        subprocess.run(["git", "add", ".gitignore"], cwd=repo, check=True, env=env)
        subprocess.run(["git", "add", "-f", "kept.txt"], cwd=repo, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=repo, check=True, env=env)
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, env=env, capture_output=True,
                                text=True).stdout.strip()
        self.assertEqual(self.module().worktree_diff(repo)[0], commit)
        head = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=repo, check=True, env=env,
                              capture_output=True, text=True).stdout.strip()
        self.assertEqual(self.module().worktree_diff(repo)[1], head)

    def test_a_change_in_the_second_of_the_index_is_in_the_diff(self) -> None:
        # The copy of the index keeps its time, so git checks the content of an entry as old as the index. The
        # ctime of a file cannot be set, so git must not compare it: a change of the ctime alone shows the change.
        git("config", "core.trustctime", "false", cwd=self.repo)
        index, path = self.repo / ".git/index", self.repo / "a.txt"
        self.write("a.txt", "aaa\n")
        stamp = path.stat().st_mtime_ns - 10 * 10**9
        os.utime(path, ns=(stamp, stamp))
        self.commit()
        os.utime(index, ns=(stamp, stamp))
        self.write("a.txt", "bbb\n")
        os.utime(path, ns=(stamp, stamp))
        self.assertIn(b"+bbb", self.module().worktree_diff(self.repo)[2])

    def test_the_first_packet_of_a_repository_has_the_worktree_tree(self) -> None:
        # The repository does not ignore .agents/log, so the script ignores it before it writes the diff file.
        self.write(".gitignore", "")
        self.write("a.txt", "x\n")
        self.commit()
        self.write("a.txt", "y\n")
        # jlog writes its run log before the recipe runs the script.
        self.write(".agents/log/just.jsonl", "{}\n")
        result = self.render("review")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("jagt saved the input tree", result.stderr)
        self.assertEqual(git("status", "--porcelain", cwd=self.repo).split(), ["M", "a.txt"])
        diffs = list((self.repo / ".agents/log/diffs").glob("*.diff"))
        self.assertEqual(len(diffs), 1)
        self.assertNotIn(b"just.jsonl", diffs[0].read_bytes())

    def test_a_linked_log_folder_gets_no_write(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        (self.repo / ".agents/log").symlink_to(outside)
        result = self.render("review")
        self.assertEqual(result.returncode, 1)
        self.assertIn("is a link", result.stderr)
        self.assertEqual(list(outside.iterdir()), [])

    def test_a_linked_agents_folder_gets_no_write(self) -> None:
        outside = self.base / "outside"
        shutil.move(str(self.repo / ".agents"), str(outside))
        (self.repo / ".agents").symlink_to(outside)
        result = self.render("review")
        self.assertEqual(result.returncode, 1)
        self.assertIn("is a link", result.stderr)
        self.assertFalse((outside / "log").exists())

    def test_a_linked_diffs_folder_gets_no_write(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        self.write(".agents/log/.gitignore", "*\n")
        (self.repo / ".agents/log/diffs").symlink_to(outside)
        result = self.render("review")
        self.assertEqual(result.returncode, 1)
        self.assertIn("is a link", result.stderr)
        self.assertEqual(list(outside.iterdir()), [])

    def test_a_link_at_the_diff_file_gets_no_write(self) -> None:
        outside = self.base / "outside.diff"
        module = self.module()
        head, tree, _ = module.worktree_diff(self.repo)
        (self.repo / ".agents/log/diffs").mkdir(parents=True)
        diff_file = self.repo / f".agents/log/diffs/{head}-{tree}.diff"
        diff_file.symlink_to(outside)
        result = self.render("review")
        # The script removes the link and writes a new file in its place.
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(outside.exists())
        self.assertFalse(diff_file.is_symlink())
        self.assertIn(b"review.md", diff_file.read_bytes())

    def test_a_file_at_the_log_folder_gives_a_message(self) -> None:
        self.write(".agents/log", "")
        result = self.render("review")
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not a folder", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_a_linked_git_folder_gets_no_write_outside(self) -> None:
        elsewhere = self.base / "store/elsewhere"
        elsewhere.mkdir(parents=True)
        shutil.move(str(self.repo / ".git"), str(elsewhere / ".git"))
        (self.repo / ".git").symlink_to(elsewhere / ".git")
        result = self.render("review")
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not in", result.stderr)
        self.assertFalse((elsewhere / ".agents").exists())

    def test_a_folder_swapped_for_a_link_during_the_diff_gets_no_write(self) -> None:
        # A link that appears while git computes the diff must not move the diff file.
        module = self.module()
        outside = self.base / "outside"
        outside.mkdir()
        real = module.worktree_diff

        def swap(root):
            result = real(root)
            diffs = self.repo / ".agents/log/diffs"
            diffs.rename(self.base / "old-diffs")
            diffs.symlink_to(outside)
            return result

        module.worktree_diff = swap
        with unittest.mock.patch.object(module.sys, "stdout"):
            module.render(self.repo, "review", [])
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(len(list((self.base / "old-diffs").glob("*.diff"))), 1)

    def test_a_worktree_installs_before_the_main_checkout_has_the_targets(self) -> None:
        # The main checkout is on a branch from before the install, so it has no .agents folder yet.
        main = self.base / "main"
        main.mkdir()
        git("init", "-q", "-b", "main", cwd=main)
        (main / "a.txt").write_text("a\n")
        subprocess.run(["git", "add", "a.txt"], cwd=main, check=True, env=self.env)
        subprocess.run(["git", "commit", "-q", "-m", "a"], cwd=main, check=True, env=self.env)
        tree = self.base / "wt"
        git("worktree", "add", "-q", "-b", "feat", str(tree), cwd=main)
        base = tree / ".agents/skills/grv/references/targets/review.md"
        base.parent.mkdir(parents=True)
        base.write_text("BASE TASK\n")
        result = self.render("review", cwd=tree)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((main / ".agents/log/.gitignore").is_file())
        self.assertFalse((tree / ".agents/log").exists())

    def test_a_hard_link_at_the_diff_file_keeps_the_outside_file(self) -> None:
        victim = self.base / "victim.txt"
        victim.write_text("keep\n")
        head, tree, _ = self.module().worktree_diff(self.repo)
        (self.repo / ".agents/log/diffs").mkdir(parents=True)
        diff_file = self.repo / f".agents/log/diffs/{head}-{tree}.diff"
        os.link(victim, diff_file)
        result = self.render("review")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(victim.read_text(), "keep\n")
        self.assertIn(b"review.md", diff_file.read_bytes())

    def test_a_worktree_of_a_linked_git_folder_writes_beside_the_real_git_folder(self) -> None:
        # From a worktree, git names the folder of the real .git as the main checkout. That folder is the person's
        # own, and the gate and jagt use the same log folder there.
        self.write("a.txt", "x\n")
        self.commit()
        real = self.base / "store/real"
        real.mkdir(parents=True)
        shutil.move(str(self.repo / ".git"), str(real / ".git"))
        (self.repo / ".git").symlink_to(real / ".git")
        git("worktree", "add", "-q", str(self.base / "wt"), cwd=self.repo)
        result = self.render("review", cwd=self.base / "wt")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(p.name for p in real.iterdir()), [".agents", ".git"])
        self.assertTrue((real / ".agents/log/.gitignore").is_file())

    def test_a_worktree_of_a_main_checkout_with_a_deleted_file_renders(self) -> None:
        self.write(".editorconfig", "x\n")
        self.commit()
        shutil.rmtree(self.repo / ".agents")
        (self.repo / ".editorconfig").unlink()
        tree = self.base / "wt"
        git("worktree", "add", "-q", str(tree), cwd=self.repo)
        result = self.render("review", cwd=tree)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.repo / ".agents/log/.gitignore").is_file())

    def test_a_worktree_of_a_bare_hub_gets_the_log_folder(self) -> None:
        # jagt 0.6.0 refuses a bare main repository, so only the part of the script is checked.
        self.write("a.txt", "x\n")
        self.commit()
        hub = self.base / "hub"
        hub.mkdir()
        git("clone", "-q", "--bare", str(self.repo), str(hub / ".git"), cwd=self.base)
        tree = hub / "wt"
        git("worktree", "add", "-q", str(tree), "main", cwd=hub / ".git")
        result = self.render("review", cwd=tree)
        self.assertTrue((hub / ".agents/log/.gitignore").is_file())
        self.assertEqual(len(list((hub / ".agents/log/diffs").glob("*.diff"))), 1)
        if result.returncode:
            self.assertIn("render failed", result.stderr)

    def test_a_log_folder_that_cannot_be_opened_names_the_cause(self) -> None:
        log = self.repo / ".agents/log"
        log.mkdir(parents=True)
        log.chmod(0)
        self.addCleanup(log.chmod, 0o755)
        result = self.render("review")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot open the folder", result.stderr)
        self.assertIn("Permission denied", result.stderr)
        self.assertNotIn("[Errno", result.stderr)

    def test_a_log_folder_that_cannot_be_written_gives_a_message(self) -> None:
        log = self.repo / ".agents/log"
        log.mkdir(parents=True)
        log.chmod(0o555)
        self.addCleanup(log.chmod, 0o755)
        result = self.render("review")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot write", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("[Errno", result.stderr)

    def test_a_diffs_folder_that_cannot_be_written_gives_a_message(self) -> None:
        diffs = self.repo / ".agents/log/diffs"
        diffs.mkdir(parents=True)
        self.write(".agents/log/.gitignore", "*\n")
        diffs.chmod(0o555)
        self.addCleanup(diffs.chmod, 0o755)
        result = self.render("review")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot write", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("[Errno", result.stderr)

    def full_disk(self, module):
        """A stand-in for os.fdopen whose writes fail as on a full disk."""
        real = module.os.fdopen

        class Full:
            def __init__(self, fd, *args, **kwargs):
                self.file = real(fd, *args, **kwargs)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.file.close()

            def write(self, data):
                raise OSError(errno.ENOSPC, "No space left on device")

        return unittest.mock.patch.object(module.os, "fdopen", Full)

    def test_a_failed_write_of_the_gitignore_leaves_no_file(self) -> None:
        module = self.module()
        with self.full_disk(module), self.assertRaises(module.Stop) as stop:
            module.prepare_log(self.repo)
        self.assertIn("No space left on device", str(stop.exception))
        self.assertFalse((self.repo / ".agents/log/.gitignore").exists())

    def test_a_failed_write_of_the_diff_stops_with_a_message(self) -> None:
        module = self.module()
        self.write(".agents/log/.gitignore", "*\n")
        with self.full_disk(module), self.assertRaises(module.Stop) as stop:
            module.render(self.repo, "review", [])
        self.assertIn("cannot write", str(stop.exception))
        self.assertIn("No space left on device", str(stop.exception))

    def test_a_dangling_link_at_the_gitignore_gets_no_write(self) -> None:
        outside = self.base / "outside.txt"
        (self.repo / ".agents/log").mkdir(parents=True)
        (self.repo / ".agents/log/.gitignore").symlink_to(outside)
        result = self.render("review")
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not a file", result.stderr)
        self.assertFalse(outside.exists())

    def test_a_folder_at_the_gitignore_stops_the_render(self) -> None:
        (self.repo / ".agents/log/.gitignore").mkdir(parents=True)
        result = self.render("review")
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not a file", result.stderr)

    def test_a_split_index_leaves_no_new_shared_index(self) -> None:
        self.write("a.txt", "x\n")
        self.commit()
        git("config", "core.splitIndex", "true", cwd=self.repo)
        # Without this, git writes no new shared index for a small change, and the test passes without the fix.
        git("config", "splitIndex.maxPercentChange", "0", cwd=self.repo)
        git("update-index", "--split-index", cwd=self.repo)
        before = sorted(p.name for p in (self.repo / ".git").glob("sharedindex.*"))
        self.write("a.txt", "y\n")
        self.write("b.txt", "z\n")
        # The diff of the script only: jagt 0.6.0 itself writes a shared index when it renders.
        diff = self.module().worktree_diff(self.repo)[2]
        self.assertIn(b"+y", diff)
        self.assertIn(b"+z", diff)
        self.assertEqual(sorted(p.name for p in (self.repo / ".git").glob("sharedindex.*")), before)

    def test_an_argument_that_starts_with_a_dash_is_an_argument(self) -> None:
        self.write(".agents/skills/gdo/references/targets/update-docs.md", "DOCS TASK\n")
        result = self.render("update-docs", "-v", "--help", "--no-save")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("argv:\n  - '-v'\n  - '--help'\n  - '--no-save'\n", result.stdout)

    def test_a_diff_against_another_head_gets_its_own_file(self) -> None:
        self.write("a.txt", "1\n")
        self.commit()
        self.write("a.txt", "2\n")
        first = self.render("review")
        self.assertEqual(first.returncode, 0, first.stderr)
        before = self.diff_of(first)
        self.commit()
        second = self.render("review")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.diff_of(second), b"")
        self.assertIn(b"+2", before)
        self.assertEqual(len(list((self.repo / ".agents/log/diffs").glob("*.diff"))), 2)

    def test_the_diff_ignores_the_diff_settings(self) -> None:
        self.write("a.txt", "plain\n")
        self.commit()
        self.write(".gitattributes", "*.txt diff=up\n")
        git("config", "diff.up.textconv", "false", cwd=self.repo)
        git("config", "diff.noprefix", "true", cwd=self.repo)
        self.write("a.txt", "changed\n")
        result = self.render("review")
        self.assertEqual(result.returncode, 0, result.stderr)
        diff = self.diff_of(result)
        self.assertIn(b"+changed", diff)
        self.assertIn(b"--- a/a.txt\n+++ b/a.txt", diff)

    def test_each_packet_says_what_its_fresh_agent_may_do(self) -> None:
        self.write(".agents/skills/gdo/references/targets/update-docs.md", "DOCS TASK\n")
        result = self.render("update-docs")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("  - change the docs that the change affects\n", result.stdout)
        self.assertIn("    - files\n    - checked\n", result.stdout)
        self.write(".agents/skills/gte/references/targets/visual-check.md", "VISUAL TASK\n")
        result = self.render("visual-check")
        self.assertIn("    - screenshots\n", result.stdout)
        self.assertIn("  - write screenshots in a temporary folder outside the repository\n", result.stdout)

    def test_a_separate_git_folder_prints_no_packet(self) -> None:
        other = self.base / "sep"
        other.mkdir()
        git("init", "-q", "--separate-git-dir", str(self.base / "sep.git"), cwd=other)
        (other / ".agents/skills/grv/references/targets").mkdir(parents=True)
        (other / ".agents/skills/grv/references/targets/review.md").write_text("BASE\n")
        result = self.render("review", cwd=other)
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not named .git", result.stderr)
        self.assertNotIn("AGENT_TASK", result.stdout)

    def test_an_open_finding_as_the_base_tasks_say_passes_the_lint(self) -> None:
        # The base tasks of review and test-review give a result with open findings the status partial and an
        # error, which jagt result lint accepts; failed would need no outputs.
        for path in ("grv/references/targets/review.md", "gte/references/targets/test-review.md"):
            text = (ROOT / ".agents/skills" / path).read_text()
            self.assertIn("the status is\n  `partial`" if "test-review" in path else "the status is `partial`", text)
            self.assertIn("`open_findings`", text)
        result = ("<<<AGENT_RESULT v1>>>\ntarget: review\nnonce: a1b2c3d4e5f60718293a4b5c6d7e8f90\nstatus: partial\n"
                  "outputs:\n  findings:\n    - summary: x\n      reason: y\nverification: []\nnotes: |\n  open: z\n"
                  "error:\n  code: open_findings\n  message: 1 open finding\nfollow_up: []\n<<<END_AGENT_RESULT>>>\n")
        lint = subprocess.run(["jagt", "result", "lint", "--expect-target", "review", "--expect-nonce",
                               "a1b2c3d4e5f60718293a4b5c6d7e8f90", "-"], input=result, capture_output=True, text=True)
        self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)

    def module(self):
        spec = importlib.util.spec_from_file_location("agentic_target", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_an_unknown_target_or_a_missing_base_task_prints_no_packet(self) -> None:
        result = self.render("deploy")
        self.assertEqual(result.returncode, 1)
        self.assertIn("deploy is not an agentic target", result.stderr)
        result = self.render("test-review")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no installed skill has references/targets/test-review.md", result.stderr)
        self.assertNotIn("AGENT_TASK", result.stdout)

    def test_the_packet_of_test_review_holds_the_result_of_test_parent(self) -> None:
        self.write(".agents/skills/gte/references/targets/test-review.md", "TEST TASK\n")
        self.commit()
        self.write("tests/test_a.py", "def test_a(): pass\n")
        result = self.render("test-review")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no result of test-parent for the tree", result.stderr)
        tree = agentic_target.worktree_diff(self.repo)[1]
        self.write(f".agents/log/test-parent/{tree}.json", '{"runs": []}\n')
        result = self.render("test-review")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"test-parent/{tree}.json", result.stdout)

    def test_two_skills_with_one_base_task_print_no_packet(self) -> None:
        self.write(".agents/skills/other/references/targets/review.md", "OTHER\n")
        result = self.render("review")
        self.assertEqual(result.returncode, 1)
        self.assertIn("two skills have references/targets/review.md (grv, other)", result.stderr)

    def test_each_target_has_its_base_task_in_this_package(self) -> None:
        own = {path.stem: path.parts[-4] for path in ROOT.glob(".agents/skills/*/references/targets/*.md")}
        module = self.module()
        # prose comes from the nossaifd skill, which the prose role installs.
        self.assertEqual(set(own) | {"prose"}, set(module.TARGETS))
        self.assertEqual(own, {"review": "grv", "test-review": "gte", "visual-check": "gte", "update-docs": "gdo",
                               "visualize": "gdo"})


if __name__ == "__main__":
    unittest.main()
