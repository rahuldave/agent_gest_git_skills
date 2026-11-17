"""CI runs just check and no other check, so a developer finds each failure of CI with just check.

The job verify of verify.yml runs just check and no other recipe, with the whole history for release-check. The job
release stays as it was: it runs just release after verify, on a push to main. The tests need just, and PyYAML.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/verify.yml"
# The recipes that just check must run: each check that CI ran before just check, and the checks of the other repos.
STEPS = ["release-check", "lint", "package-lint", "stack-rebase-lab", "install-test", "source-archive", "diff-check"]
# The steps of the job verify that set up a clone or a program, and the step that runs just check.
SETUP = {"Get jnterfaces, whose link checker the lint runs and whose installer install-test runs",
         "Install jlog v0.2.0, which the jnterfaces installer needs"}
CHECK = "Check the release, the lint, the manifest, the labs, the install, the source archive and the diff"
# The actions of the job verify. A check in an action would be a check that just check does not run.
VERIFY_ACTIONS = ["actions/checkout@v4", "astral-sh/setup-uv@v6", "extractions/setup-just@v3", "actions/cache@v4",
                  "actions/upload-artifact@v4"]
# The steps of the job release, as they were before just check came: CI tags each release after verify passed.
RELEASE_STEPS = [
    {"uses": "actions/checkout@v4", "with": {"fetch-depth": 0}},
    {"uses": "astral-sh/setup-uv@v6"},
    {"uses": "extractions/setup-just@v3"},
    {"name": "Name the author of the tag",
     "run": 'git config user.name "github-actions[bot]"\n'
            'git config user.email "41898282+github-actions[bot]@users.noreply.github.com"\n'},
    {"name": "Tag the release", "run": "just release"},
]
# The tag of jlog that the CI of jnterfaces pins.
JLOG = "v0.2.0"


def check_steps() -> list[str]:
    dump = subprocess.run(["just", "--justfile", str(ROOT / "Justfile"), "--dump", "--dump-format", "json"],
                          check=True, capture_output=True, text=True).stdout
    check = json.loads(dump)["recipes"]["check"]
    return [dependency["recipe"] for dependency in check["dependencies"]]


def runs(job: dict) -> list[str]:
    return [line.strip() for step in job["steps"] for line in (step.get("run") or "").splitlines() if line.strip()]


@unittest.skipUnless(shutil.which("just"), "needs just")
class CheckTests(unittest.TestCase):
    def test_check_runs_each_step_in_order(self) -> None:
        self.assertEqual(check_steps(), STEPS)


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]

    def test_verify_runs_just_check_and_no_other_command_but_the_setup(self) -> None:
        # Each step with run is the setup of a program or a clone, or the bare line just check.
        runs = {step["name"]: step["run"] for step in self.jobs["verify"]["steps"] if "run" in step}
        self.assertEqual(set(runs), SETUP | {CHECK})
        self.assertEqual(runs[CHECK].strip(), "just check")
        for name in SETUP:
            self.assertNotRegex(runs[name], r"\bjust\b|scripts/\S+\.(sh|py)|git archive|sha256sum|shasum", name)

    def test_verify_checks_out_the_pinned_jnterfaces(self) -> None:
        commit = (ROOT / "scripts/jnterfaces_commit").read_text().strip()
        self.assertRegex(commit, r"^[0-9a-f]{40}$")
        self.assertIn('git -C "$RUNNER_TEMP/jnterfaces" checkout --quiet "$(cat scripts/jnterfaces_commit)"',
                      runs(self.jobs["verify"]))

    def test_verify_uses_no_action_but_the_setup_and_the_upload(self) -> None:
        steps = self.jobs["verify"]["steps"]
        self.assertEqual([step["uses"] for step in steps if "uses" in step], VERIFY_ACTIONS)
        for step in steps:
            self.assertNotIn("continue-on-error", step, step.get("name") or step.get("uses"))
        self.assertNotIn("continue-on-error", self.jobs["verify"])

    def test_verify_has_the_whole_history_for_release_check(self) -> None:
        checkout = next(step for step in self.jobs["verify"]["steps"]
                        if step.get("uses", "").startswith("actions/checkout@"))
        self.assertEqual(checkout.get("with", {}).get("fetch-depth"), 0)

    def test_verify_pins_jlog_as_jnterfaces_does(self) -> None:
        steps = self.jobs["verify"]["steps"]
        installs = [line for line in runs(self.jobs["verify"]) if "rahuldave/jlog" in line]
        self.assertEqual(installs, [f"cargo install --locked --git https://github.com/rahuldave/jlog --tag {JLOG} jlog"])
        cache = next(step for step in steps if step.get("uses", "").startswith("actions/cache@"))
        self.assertEqual(cache["with"]["key"], f"jlog-{JLOG}-${{{{ runner.os }}}}")

    def test_verify_uploads_the_archive_of_just_check(self) -> None:
        upload = self.jobs["verify"]["steps"][-1]
        self.assertTrue(upload["uses"].startswith("actions/upload-artifact@"))
        self.assertEqual(upload["with"]["path"], "dist/")

    def test_release_runs_just_release_after_verify_on_main(self) -> None:
        job = self.jobs["release"]
        self.assertEqual(job["needs"], "verify")
        self.assertIn("github.event_name == 'push'", job["if"])
        self.assertIn("github.ref == 'refs/heads/main'", job["if"])
        self.assertEqual(job["permissions"], {"contents": "write"})
        self.assertEqual(job["steps"][-1]["run"], "just release")
        self.assertEqual(job["steps"], RELEASE_STEPS)


class PinWarningTests(unittest.TestCase):
    """warn_jnterfaces_pin.sh warns when the jnterfaces clone is not what CI tests, and never fails."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
        self.git = lambda *args: subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t", "-c",
                                                 "user.email=t@example.com", *args], check=True, capture_output=True,
                                                text=True, env={**os.environ, **env}).stdout.strip()
        self.git("init", "-q")
        self.git("commit", "-q", "--allow-empty", "-m", "start")
        self.head = self.git("rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def warn(self, pin: str) -> str:
        run = subprocess.run([str(ROOT / "scripts/warn_jnterfaces_pin.sh"), str(self.repo), pin], capture_output=True,
                             text=True)
        self.assertEqual(run.returncode, 0)
        return run.stderr

    def test_a_clone_at_the_pin_gives_no_warning(self) -> None:
        self.assertEqual(self.warn(self.head), "")

    def test_another_commit_warns(self) -> None:
        self.assertIn("is not at", self.warn("0" * 40))

    def test_changes_that_are_not_committed_warn(self) -> None:
        (self.repo / "x").write_text("x")
        self.assertIn("not committed", self.warn(self.head))

    def test_a_folder_that_is_no_clone_warns(self) -> None:
        self.tmp2 = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp2.cleanup)
        run = subprocess.run([str(ROOT / "scripts/warn_jnterfaces_pin.sh"), self.tmp2.name], capture_output=True,
                             text=True, env={**os.environ, "GIT_CEILING_DIRECTORIES": str(Path(self.tmp2.name).parent)})
        self.assertEqual(run.returncode, 0)
        self.assertIn("is not at", run.stderr)


if __name__ == "__main__":
    unittest.main()
