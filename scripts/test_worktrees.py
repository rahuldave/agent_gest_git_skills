"""Check the worktree script of gtw and the hooks that read the tasker variant, in scratch repositories."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/gtw/scripts/worktree.py"
RECIPES = ROOT / ".agents/just/roles/agent_gest_git_skills.just"


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def age_worktree(folder: Path, hours: float) -> None:
    """Make the worktree look idle: set the times of its admin files and of its top files and folders."""
    gitdir = Path(git("rev-parse", "--absolute-git-dir", cwd=folder).strip())
    then = time.time() - hours * 3600
    items = [gitdir / name for name in ("index", "HEAD", "logs/HEAD")] + list(folder.iterdir())
    for item in items:
        if os.path.lexists(item):
            os.utime(item, (then, then), follow_symlinks=False)


class WorktreeScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="gest-worktree-test-")
        self.addCleanup(scratch.cleanup)
        self.base = Path(scratch.name).resolve()
        self.repo = self.base / "proj"
        self.shelf = self.base / "proj.worktrees"
        git("init", "-qb", "main", str(self.repo), cwd=self.base)
        git("config", "user.name", "worktree-test", cwd=self.repo)
        git("config", "user.email", "worktree-test@example.invalid", cwd=self.repo)
        (self.repo / ".gitignore").write_text(".env\ndata\nbig/\n*.log\n")
        (self.repo / ".worktreeinclude").write_text(".env\n*.log\nnotes.txt\n")
        (self.repo / ".worktreelink").write_text("# shared inputs\ndata\n")
        (self.repo / "notes.txt").write_text("tracked\n")
        git("add", ".", cwd=self.repo)
        git("commit", "-qm", "init", cwd=self.repo)
        (self.repo / ".env").write_text("KEY=1\n")
        (self.repo / "run.log").write_text("log\n")
        (self.repo / "data").mkdir()
        (self.repo / "data/rows.csv").write_text("a,b\n")

    def run_script(self, *args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
        done = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.repo, capture_output=True,
                              text=True)
        if check:
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done

    def age(self, folder: Path, hours: float) -> None:
        age_worktree(folder, hours)

    def commit(self, folder: Path, name: str) -> None:
        (folder / name).write_text(name + "\n")
        git("add", name, cwd=folder)
        git("commit", "-qm", name, cwd=folder)

    # mode

    def test_mode_is_git_without_a_record_and_reads_the_variant(self) -> None:
        self.assertEqual(self.run_script("mode").stdout.strip(), "git")
        (self.repo / ".agents").mkdir()
        (self.repo / ".agents/stack.json").write_text(json.dumps({"variants": {"tasker": "gitwt"}}))
        self.assertEqual(self.run_script("mode").stdout.strip(), "gitwt")
        (self.repo / ".agents/stack.json").write_text(json.dumps({"variants": {"tasker": "jj"}}))
        self.assertEqual(self.run_script("mode").stdout.strip(), "git")
        (self.repo / ".agents/stack.json").write_text("not json")
        self.assertEqual(self.run_script("mode").stdout.strip(), "git")

    # new and sync

    def test_new_makes_the_branch_beside_the_repository_and_sets_it_up(self) -> None:
        out = self.run_script("new", "topic/one").stdout
        folder = self.shelf / "topic-one"
        self.assertIn("new branch topic/one from main", out)
        self.assertEqual(git("branch", "--show-current", cwd=folder).strip(), "topic/one")
        # An ignored file that .worktreeinclude names is copied; a tracked one comes from git, not from the copy.
        self.assertEqual((folder / ".env").read_text(), "KEY=1\n")
        self.assertFalse((folder / ".env").is_symlink())
        self.assertTrue((folder / "run.log").is_file())
        self.assertEqual((folder / "notes.txt").read_text(), "tracked\n")
        # The data folder is a link to the main checkout, and git ignores the link.
        self.assertTrue((folder / "data").is_symlink())
        self.assertEqual(Path(os.readlink(folder / "data")), self.repo / "data")
        self.assertEqual(git("status", "--porcelain", cwd=folder), "")

    def test_new_takes_a_base_and_an_existing_branch(self) -> None:
        git("branch", "other", cwd=self.repo)
        self.commit(self.repo, "later.txt")
        self.run_script("new", "from-other", "other")
        self.assertFalse((self.shelf / "from-other/later.txt").exists())
        self.run_script("new", "other2", "main")
        self.assertTrue((self.shelf / "other2/later.txt").exists())
        git("branch", "kept", cwd=self.repo)
        self.assertIn("for the branch kept", self.run_script("new", "kept").stdout)
        self.assertNotEqual(self.run_script("new", "kept", "main", check=False).returncode, 0)

    def test_new_refuses_a_bad_name_and_a_taken_folder(self) -> None:
        self.assertIn("not a valid branch name", self.run_script("new", "bad..name", check=False).stderr)
        (self.shelf / "taken").mkdir(parents=True)
        self.assertIn("is there already", self.run_script("new", "taken", check=False).stderr)
        self.assertNotIn("taken", git("branch", "--list", "taken", cwd=self.repo))

    def test_new_runs_just_setup_unless_told_not_to(self) -> None:
        if not shutil.which("just"):
            self.skipTest("just is not installed")
        (self.repo / "Justfile").write_text("setup:\n    touch set-up.marker\n")
        (self.repo / ".gitignore").write_text((self.repo / ".gitignore").read_text() + "*.marker\n")
        git("add", ".", cwd=self.repo)
        git("commit", "-qm", "justfile", cwd=self.repo)
        self.run_script("new", "with-setup")
        self.assertTrue((self.shelf / "with-setup/set-up.marker").exists())
        self.run_script("new", "without-setup", "--no-setup")
        self.assertFalse((self.shelf / "without-setup/set-up.marker").exists())

    def test_sync_refuses_the_main_checkout(self) -> None:
        self.assertIn("main checkout", self.run_script("sync", check=False).stderr)

    def test_sync_keeps_what_the_worktree_has_and_fills_what_it_lacks(self) -> None:
        self.run_script("new", "t", "--no-setup")
        folder = self.shelf / "t"
        (folder / ".env").write_text("KEY=mine\n")
        (folder / "run.log").unlink()
        out = self.run_script("sync", cwd=folder).stdout
        self.assertIn("Kept .env", out)
        self.assertEqual((folder / ".env").read_text(), "KEY=mine\n")
        self.assertTrue((folder / "run.log").is_file())

    def test_sync_works_in_a_worktree_that_another_tool_made(self) -> None:
        folder = self.base / "elsewhere"
        git("worktree", "add", "-q", "-b", "claude-made", str(folder), cwd=self.repo)
        self.run_script("sync", cwd=folder)
        self.assertTrue((folder / "data").is_symlink())
        self.assertTrue((folder / ".env").is_file())

    def test_a_link_that_git_does_not_ignore_gets_a_warning(self) -> None:
        (self.repo / ".worktreelink").write_text("big\n")
        (self.repo / "big").mkdir()
        (self.repo / "big/x").write_text("x\n")
        out = self.run_script("new", "t", "--no-setup").stdout
        self.assertIn("Add /big without a final /", out)

    def test_link_paths_must_stay_inside_the_project_and_be_untracked(self) -> None:
        (self.repo / ".worktreelink").write_text("../outside\n")
        self.assertIn("plain path inside the project", self.run_script("new", "t1", "--no-setup",
                                                                         check=False).stderr)
        (self.repo / ".worktreelink").write_text("notes.txt\n")
        out = self.run_script("sync", cwd=self.shelf / "t1").stdout
        self.assertIn("git tracks it", out)
        self.assertFalse((self.shelf / "t1/notes.txt").is_symlink())

    # list and prune

    def test_prune_removes_only_clean_merged_idle_worktrees(self) -> None:
        for name in ("merged", "dirty", "open", "young", "squashed"):
            self.run_script("new", name, "--no-setup")
        self.commit(self.shelf / "merged", "m.txt")
        git("merge", "-q", "--ff-only", "merged", cwd=self.repo)
        self.commit(self.shelf / "open", "o.txt")
        (self.shelf / "dirty/new.txt").write_text("not committed\n")
        self.commit(self.shelf / "squashed", "s1.txt")
        self.commit(self.shelf / "squashed", "s2.txt")
        git("merge", "-q", "--squash", "squashed", cwd=self.repo)
        git("commit", "-qm", "squash", cwd=self.repo)
        for name in ("merged", "dirty", "open", "squashed"):
            self.age(self.shelf / name, 5)
        listing = self.run_script("list").stdout
        self.assertIn("(merged)  clean, merged  ready to prune", listing)
        self.assertIn("(young)  clean  stays: it changed", listing)
        self.assertIn("ignored files, which a removal deletes: .env, data, run.log", listing)
        dry = self.run_script("prune", "--dry-run").stdout
        self.assertIn("Would remove", dry)
        self.assertIn("Its ignored files go too: .env, data, run.log", dry)
        self.assertTrue((self.shelf / "merged").is_dir())
        out = self.run_script("prune").stdout
        self.assertFalse((self.shelf / "merged").exists())
        self.assertFalse((self.shelf / "squashed").exists())
        for name in ("dirty", "open", "young"):
            self.assertTrue((self.shelf / name).is_dir(), name)
        self.assertIn("it has changes or new files", out)
        self.assertIn("its commits are not in main", out)
        # The link went with the worktree; the data in the main checkout stays.
        self.assertEqual((self.repo / "data/rows.csv").read_text(), "a,b\n")
        # Branches stay.
        self.assertIn("merged", git("branch", "--list", "merged", cwd=self.repo))
        self.run_script("prune", "--min-age", "0")
        self.assertFalse((self.shelf / "young").exists())

    def test_a_squash_that_a_revert_took_out_is_not_merged(self) -> None:
        self.run_script("new", "gone-again", "--no-setup")
        folder = self.shelf / "gone-again"
        self.commit(folder, "w.txt")
        git("merge", "-q", "--squash", "gone-again", cwd=self.repo)
        git("commit", "-qm", "squash", cwd=self.repo)
        git("revert", "--no-edit", "HEAD", cwd=self.repo)
        self.age(folder, 5)
        self.assertIn("its commits are not in main", self.run_script("prune").stdout)
        self.assertTrue(folder.is_dir())

    def test_a_whitespace_change_is_not_merged_by_a_different_one(self) -> None:
        (self.repo / "f.py").write_text("if x:\n    a()\n    b()\nc()\n")
        git("add", "f.py", cwd=self.repo)
        git("commit", "-qm", "f", cwd=self.repo)
        self.run_script("new", "dedent", "--no-setup")
        folder = self.shelf / "dedent"
        (folder / "f.py").write_text("if x:\n    a()\nb()\nc()\n")
        git("commit", "-qam", "dedent b", cwd=folder)
        (self.repo / "f.py").write_text("if x:\n    a()\n        b()\nc()\n")
        git("commit", "-qam", "indent b", cwd=self.repo)
        self.age(folder, 5)
        self.assertIn("its commits are not in main", self.run_script("prune").stdout)
        self.assertTrue(folder.is_dir())

    def test_a_detached_worktree_whose_commits_are_on_no_branch_stays(self) -> None:
        folder = self.shelf / "det"
        git("worktree", "add", "-q", "--detach", str(folder), "main", cwd=self.repo)
        (folder / "w.txt").write_text("w\n")
        git("add", "w.txt", cwd=folder)
        git("commit", "-qm", "w", cwd=folder)
        git("merge", "-q", "--squash", git("rev-parse", "HEAD", cwd=folder).strip(), cwd=self.repo)
        git("commit", "-qm", "squash", cwd=self.repo)
        self.age(folder, 5)
        self.assertIn("its commits are on no branch", self.run_script("prune").stdout)
        self.assertTrue(folder.is_dir())

    def test_ignored_work_keeps_a_worktree_unless_asked(self) -> None:
        self.run_script("new", "exp", "--no-setup")
        folder = self.shelf / "exp"
        (folder / ".env").write_text("KEY=tuned\n")
        (folder / "out.log").write_text("an output\n")
        self.age(folder, 5)
        self.assertEqual(self.run_script("list", "--report").stdout, "")
        out = self.run_script("prune").stdout
        self.assertIn("ignored files that setup did not put there", out)
        self.assertTrue(folder.is_dir())
        self.run_script("prune", "--with-ignored")
        self.assertFalse(folder.exists())

    def test_a_new_output_makes_a_worktree_young(self) -> None:
        self.run_script("new", "busy", "--no-setup")
        folder = self.shelf / "busy"
        (folder / "big").mkdir()
        self.age(folder, 5)
        (folder / "big/run.csv").write_text("1\n")
        self.assertIn("stays: it changed 0.0 hours ago", self.run_script("list", "--with-ignored").stdout)

    def test_prune_removes_a_detached_review_worktree_and_the_empty_shelf(self) -> None:
        folder = self.shelf / "review"
        git("worktree", "add", "-q", "--detach", str(folder), "HEAD", cwd=self.repo)
        self.age(folder, 5)
        self.assertIn("detached at", self.run_script("list").stdout)
        self.run_script("prune")
        self.assertFalse(self.shelf.exists())

    def test_prune_keeps_the_worktree_you_are_in_and_a_locked_one(self) -> None:
        self.run_script("new", "here", "--no-setup")
        self.run_script("new", "locked", "--no-setup")
        git("worktree", "lock", str(self.shelf / "locked"), cwd=self.repo)
        out = self.run_script("prune", "--min-age", "0", cwd=self.shelf / "here").stdout
        self.assertIn("you are in it", out)
        self.assertIn("it is locked", out)
        self.assertTrue((self.shelf / "here").is_dir())

    def test_prune_clears_the_entry_of_a_deleted_folder(self) -> None:
        self.run_script("new", "gone", "--no-setup")
        shutil.rmtree(self.shelf / "gone")
        self.assertIn("gone", git("worktree", "list", cwd=self.repo))
        self.run_script("prune")
        self.assertNotIn("gone", git("worktree", "list", cwd=self.repo))

    def test_report_speaks_only_when_a_worktree_is_ready(self) -> None:
        self.run_script("new", "young", "--no-setup")
        self.assertEqual(self.run_script("list", "--report").stdout, "")
        self.age(self.shelf / "young", 5)
        self.assertIn("just worktrees-prune removes them", self.run_script("list", "--report").stdout)

    def test_bad_arguments_fail(self) -> None:
        self.assertEqual(self.run_script("prune", "--force", check=False).returncode, 1)
        self.assertEqual(self.run_script("prune", "--min-age", "soon", check=False).returncode, 1)
        self.assertEqual(self.run_script("new", "x", "--min-age", "1", check=False).returncode, 1)
        self.assertEqual(self.run_script("frob", check=False).returncode, 2)

    def test_min_age_must_be_a_finite_number(self) -> None:
        for value in ("nan", "inf", "-1"):
            self.assertEqual(self.run_script("prune", "--min-age", value, check=False).returncode, 1, value)

    def test_a_linked_include_file_is_copied_as_its_content(self) -> None:
        (self.repo / ".gitignore").write_text((self.repo / ".gitignore").read_text() + "conf/\n")
        git("commit", "-qam", "conf", cwd=self.repo)
        (self.repo / "conf").mkdir()
        (self.repo / "conf/real.env").write_text("REAL=1\n")
        (self.repo / ".env").unlink()
        (self.repo / ".env").symlink_to("conf/real.env")
        self.run_script("new", "t", "--no-setup")
        copy = self.shelf / "t/.env"
        self.assertFalse(copy.is_symlink())
        self.assertEqual(copy.read_text(), "REAL=1\n")

    def test_a_link_that_cannot_be_made_is_skipped(self) -> None:
        (self.repo / ".worktreelink").write_text(".gitignore/x\ndata\n")
        out = self.run_script("new", "t", "--no-setup").stdout
        self.assertIn("Skipped the link .gitignore/x", out)
        self.assertTrue((self.shelf / "t/data").is_symlink())

    def test_an_odd_record_means_git(self) -> None:
        (self.repo / ".agents").mkdir()
        for record in ({"variants": ["gitwt"]}, ["x"], {"variants": {"tasker": 3}}):
            (self.repo / ".agents/stack.json").write_text(json.dumps(record))
            self.assertEqual(self.run_script("mode").stdout.strip(), "git")

    def test_odd_worktree_paths_are_read_and_reported_safely(self) -> None:
        for name in ("new\nline", "tab\tbed"):
            folder = self.base / name
            git("worktree", "add", "-q", "--detach", str(folder), "HEAD", cwd=self.repo)
            self.age(folder, 5)
        listing = self.run_script("list").stdout
        self.assertNotIn("missing", listing)
        report = self.run_script("list", "--report").stdout
        self.assertIn("new?line", report)
        self.assertIn("tab?bed", report)

    def test_the_recipes_run_the_script(self) -> None:
        if not shutil.which("just") or not shutil.which("uv"):
            self.skipTest("just or uv is not installed")
        target = self.repo / ".agents/skills/gtw/scripts"
        target.mkdir(parents=True)
        shutil.copy(SCRIPT, target)
        done = subprocess.run(["just", "--justfile", str(RECIPES), "--working-directory", str(self.repo),
                               "worktree-new", "via-just", "--no-setup"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.shelf / "via-just").is_dir())


class TaskerHookTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="gest-tasker-hook-test-")
        self.addCleanup(scratch.cleanup)
        self.base = Path(scratch.name).resolve()
        self.repo = self.base / "repo"
        git("init", "-qb", "main", str(self.repo), cwd=self.base)
        git("config", "user.name", "hook-test", cwd=self.repo)
        git("config", "user.email", "hook-test@example.invalid", cwd=self.repo)
        git("commit", "-q", "--allow-empty", "-m", "init", cwd=self.repo)
        # A fake but, so the GitButler checks do not depend on the machine.
        self.bin = self.base / "bin"
        self.bin.mkdir()
        (self.bin / "but").write_text("#!/bin/sh\nexit 0\n")
        (self.bin / "but").chmod(0o755)

    def variant(self, name: str) -> None:
        (self.repo / ".agents").mkdir(exist_ok=True)
        (self.repo / ".agents/stack.json").write_text(json.dumps(
            {"version": 2, "choices": {"tasker": True}, "variants": {"tasker": name}}, indent=2) + "\n")

    def hook(self, path: str, payload: dict | None = None, cwd: Path | None = None, but: bool = True) -> str:
        env = os.environ.copy()
        env.pop("GEST_VCS_EXECUTION", None)
        env["CLAUDE_PROJECT_DIR"] = str(cwd or self.repo)
        env["PATH"] = (f"{self.bin}{os.pathsep}" if but else "") + "/usr/bin:/bin:" + os.path.dirname(
            shutil.which("uv") or "/usr/bin")
        done = subprocess.run(["bash", str(ROOT / path)], input=json.dumps(payload or {}), text=True,
                              capture_output=True, cwd=cwd or self.repo, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_gitbutler_context_speaks_only_in_an_active_workspace(self) -> None:
        hook = ".claude/hooks/gitbutler-vcs-context.sh"
        self.assertEqual(self.hook(hook), "")
        git("switch", "-qc", "gitbutler/workspace", cwd=self.repo)
        self.assertEqual(self.hook(hook, but=False), "")
        self.assertIn("GitButler VCS Context", self.hook(hook))
        self.variant("gitwt")
        self.assertEqual(self.hook(hook), "")

    def test_codex_session_start_names_gitbutler_only_in_an_active_workspace(self) -> None:
        hook = ".codex/hooks/session-start.sh"
        self.assertNotIn("GitButler", self.hook(hook))
        git("switch", "-qc", "gitbutler/workspace", cwd=self.repo)
        self.assertIn("GitButler owns this workspace", self.hook(hook))

    def test_session_start_names_the_variant(self) -> None:
        for hook in (".claude/hooks/session-start.sh", ".codex/hooks/session-start.sh"):
            self.assertIn("Tasker variant git:", json.loads(self.hook(hook))["hookSpecificOutput"]["additionalContext"])
        self.variant("gitwt")
        for hook in (".claude/hooks/session-start.sh", ".codex/hooks/session-start.sh"):
            self.assertIn("Tasker variant gitwt:", json.loads(self.hook(hook))["hookSpecificOutput"]["additionalContext"])

    def test_session_start_reports_worktrees_ready_to_prune(self) -> None:
        if not shutil.which("uv"):
            self.skipTest("uv is not installed")
        target = self.repo / ".agents/skills/gtw/scripts"
        target.mkdir(parents=True)
        shutil.copy(SCRIPT, target)
        folder = self.base / "review"
        git("worktree", "add", "-q", "--detach", str(folder), "HEAD", cwd=self.repo)
        age_worktree(folder, 5)
        for hook in (".claude/hooks/session-start.sh", ".codex/hooks/session-start.sh"):
            text = json.loads(self.hook(hook))["hookSpecificOutput"]["additionalContext"]
            self.assertIn(str(folder), text)
            self.assertIn("remove them only when the user asks", text)
        self.assertTrue(folder.is_dir())

    def test_a_commit_in_the_main_checkout_under_gitwt_gets_a_warning(self) -> None:
        cases = {".claude/hooks/raw-git-write-guard.sh": {"command": "git commit -m x"},
                 ".codex/hooks/raw-git-write-guard.sh": {"tool_input": {"cmd": "git commit -m x"}}}
        for hook, payload in cases.items():
            self.assertEqual(self.hook(hook, payload), "")
        self.variant("gitwt")
        for hook, payload in cases.items():
            out = json.loads(self.hook(hook, payload))
            self.assertNotIn("permissionDecision", json.dumps(out))
            self.assertIn("gitwt", json.dumps(out))
        self.assertIn("additionalContext", self.hook(".claude/hooks/raw-git-write-guard.sh",
                                                     cases[".claude/hooks/raw-git-write-guard.sh"]))
        self.assertIn("systemMessage", self.hook(".codex/hooks/raw-git-write-guard.sh",
                                                 cases[".codex/hooks/raw-git-write-guard.sh"]))
        # Other commands, and a commit in a worktree, get no warning.
        self.assertEqual(self.hook(".claude/hooks/raw-git-write-guard.sh", {"command": "git status"}), "")
        folder = self.base / "wt"
        git("worktree", "add", "-q", "-b", "wt", str(folder), cwd=self.repo)
        for hook, payload in cases.items():
            self.assertEqual(self.hook(hook, payload, cwd=folder), "")

    def test_the_gitbutler_block_wins_over_the_gitwt_warning(self) -> None:
        self.variant("gitwt")
        git("switch", "-qc", "gitbutler/workspace", cwd=self.repo)
        for hook, payload in ((".claude/hooks/raw-git-write-guard.sh",
                               {"command": "git commit -m x && git push --force origin main"}),
                              (".codex/hooks/raw-git-write-guard.sh",
                               {"tool_input": {"cmd": "git commit -m x && git push --force origin main"}})):
            self.assertIn('"permissionDecision":"deny"', self.hook(hook, payload))

    def test_the_warning_follows_git_c_and_needs_a_repository(self) -> None:
        self.variant("gitwt")
        hook = ".claude/hooks/raw-git-write-guard.sh"
        # A project commits its record, so each worktree has it.
        git("add", ".agents", cwd=self.repo)
        git("commit", "-qm", "record", cwd=self.repo)
        folder = self.base / "wt"
        git("worktree", "add", "-q", "-b", "wt", str(folder), cwd=self.repo)
        self.assertEqual(self.hook(hook, {"command": f"git -C {folder} commit -m x"}), "")
        self.assertIn("gitwt", self.hook(hook, {"command": f"git -C {self.repo} commit -m x"}, cwd=folder))
        self.assertIn("gitwt", self.hook(hook, {"command": "git -c user.name=a commit -m x"}))
        plain = self.base / "plain"
        (plain / ".agents").mkdir(parents=True)
        shutil.copy(self.repo / ".agents/stack.json", plain / ".agents/stack.json")
        self.assertEqual(self.hook(hook, {"command": "git commit -m x"}, cwd=plain), "")

    def test_session_start_report_survives_an_old_python_version_file_and_odd_paths(self) -> None:
        if not shutil.which("uv"):
            self.skipTest("uv is not installed")
        target = self.repo / ".agents/skills/gtw/scripts"
        target.mkdir(parents=True)
        shutil.copy(SCRIPT, target)
        (self.repo / ".python-version").write_text("3.8\n")
        folder = self.base / "tab\tbed"
        git("worktree", "add", "-q", "--detach", str(folder), "HEAD", cwd=self.repo)
        age_worktree(folder, 5)
        for hook in (".claude/hooks/session-start.sh", ".codex/hooks/session-start.sh"):
            text = json.loads(self.hook(hook))["hookSpecificOutput"]["additionalContext"]
            self.assertIn("tab?bed", text)


if __name__ == "__main__":
    unittest.main()
