"""Check the Rust steps of the CI starters of gsu: github-check.yml and github-release.yml.

The Rust steps run only in a project with a toolchain file, rust-toolchain.toml or rust-toolchain, as the docs-publish
workflow of jnterfaces does. They read the toolchain from the file and name no channel, restore a cache of the build,
and save it only on a push to main. A project in another language skips each Rust step. The tests parse the YAML with PyYAML, and run the shell of the toolchain steps with bash, a fake rustup and
Python 3.11 or later, for tomllib.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / ".agents/skills/gsu/assets/templates"
STARTERS = ("github-check.yml", "github-release.yml")
# The job of each starter that runs the checks, and so has the cache.
CHECK_JOBS = {"github-check.yml": "ci", "github-release.yml": "check"}
INSTALL = "Install the Rust toolchain of rust-toolchain.toml"
# The condition of the install, as in the docs-publish workflow of jnterfaces.
HAS_TOOLCHAIN = "hashFiles('rust-toolchain.toml', 'rust-toolchain') != ''"
PATHS = ["~/.cargo/registry/index", "~/.cargo/registry/cache", "~/.cargo/git/db", "target/"]
PREFIX = "${{ runner.os }}-${{ runner.arch }}-rust-${{ steps.rust.outputs.toolchain }}-${{ github.job }}-"
KEY = PREFIX + "${{ hashFiles('**/Cargo.lock') }}"
RUST = "steps.rust.outputs.toolchain != ''"
SAVE_IF = (f"{RUST} && github.event_name == 'push' && github.ref == 'refs/heads/main' && "
           "steps.rust-cache.outputs.cache-hit != 'true'")
# The values of an expression that change on each run. A CARGO* or RUST* variable with one of them makes the
# coverage build of jnprofile-rust clean the whole build on each run.
PER_RUN = re.compile(r"github\.(run_id|run_number|run_attempt|sha|event\.|head_ref|ref)|steps\.|runner\.temp|"
                     r"\$\(|date|\$RANDOM")


def starter(name: str) -> dict:
    return yaml.safe_load((TEMPLATES / name).read_text())


def step(job: dict, name: str) -> dict:
    [found] = [each for each in job["steps"] if each.get("name") == name]
    return found


def runs(data: dict) -> list[str]:
    """Each line of each run of each job, stripped."""
    return [line.strip() for job in data["jobs"].values() for each in job["steps"]
            for line in (each.get("run") or "").splitlines()]


def rust_variables(data: dict) -> list[str]:
    """The settings of DATA, a workflow, that would make the coverage build cold or pick another toolchain: a CARGO*
    or RUST* variable from a value that changes per run, RUSTUP_TOOLCHAIN, or a variable of rust that a step writes
    to GITHUB_ENV."""
    findings = []
    jobs = list((data.get("jobs") or {}).values())
    places = [data.get("env") or {}] + [job.get("env") or {} for job in jobs] + [
        each.get("env") or {} for job in jobs for each in job.get("steps", [])]
    for env in places:
        for key, value in env.items():
            if key == "RUSTUP_TOOLCHAIN":
                findings.append("RUSTUP_TOOLCHAIN takes the place of rust-toolchain.toml")
            elif key.startswith(("CARGO", "RUST")) and PER_RUN.search(str(value)):
                findings.append(f"{key} changes on each run")
    for job in jobs:
        for each in job.get("steps", []):
            for line in (each.get("run") or "").splitlines():
                if re.search(r'(CARGO|RUST)\w*=.*>>\s*"?\$GITHUB_ENV', line):
                    findings.append(f"a step writes a variable of rust: {line.strip()}")
                if re.search(r'^\s*(export\s+)?RUSTUP_TOOLCHAIN=', line):
                    findings.append(f"a step sets RUSTUP_TOOLCHAIN: {line.strip()}")
    return findings


def paths(found: dict) -> list[str]:
    return found["with"]["path"].split()


class CacheTests(unittest.TestCase):
    def test_the_check_job_of_release_restores_before_the_check_and_saves_after_it(self) -> None:
        job = starter("github-release.yml")["jobs"]["check"]
        names = [each.get("name") or each.get("uses") for each in job["steps"]]
        restore, save = step(job, "Restore the Rust cache"), step(job, "Save the Rust cache")
        self.assertEqual(save["uses"], "actions/cache/save@v4")
        self.assertLess(names.index("Restore the Rust cache"), names.index("Check"))
        self.assertGreater(names.index("Save the Rust cache"), names.index("Check"))
        self.assertEqual(paths(save), PATHS)
        # The save writes the key of the restore, so a Cargo.lock that the build writes changes nothing.
        self.assertEqual(save["with"]["key"], "${{ steps.rust-cache.outputs.cache-primary-key }}")
        self.assertEqual(save["if"], SAVE_IF)

    def test_each_check_job_restores_with_the_key_of_jnterfaces(self) -> None:
        for name, job_name in CHECK_JOBS.items():
            with self.subTest(starter=name):
                job = starter(name)["jobs"][job_name]
                names = [each.get("name") or each.get("uses") for each in job["steps"]]
                restore = step(job, "Restore the Rust cache")
                self.assertEqual(restore["uses"], "actions/cache/restore@v4")
                self.assertEqual(restore["id"], "rust-cache")
                self.assertEqual(restore["if"], RUST)
                self.assertLess(names.index(INSTALL), names.index("Restore the Rust cache"))
                self.assertEqual(paths(restore), PATHS)
                self.assertEqual(restore["with"]["key"], KEY)
                self.assertEqual(restore["with"]["restore-keys"].strip(), PREFIX)

    def test_check_yml_runs_only_on_pull_requests_and_saves_nothing(self) -> None:
        flow = starter("github-check.yml")
        self.assertEqual(list(flow[True]), ["pull_request"])
        names = [each.get("name") for each in flow["jobs"]["ci"]["steps"]]
        self.assertNotIn("Save the Rust cache", names)

    def test_no_job_of_a_pull_request_saves_the_cache(self) -> None:
        for name in STARTERS:
            for job_name, job in starter(name)["jobs"].items():
                for each in job["steps"]:
                    if each.get("uses", "").startswith("actions/cache"):
                        with self.subTest(starter=name, job=job_name, step=each.get("name")):
                            # Only the two actions of the design, never actions/cache, which saves at the end.
                            self.assertIn(each["uses"], ("actions/cache/restore@v4", "actions/cache/save@v4"))
                            if each["uses"].startswith("actions/cache/save"):
                                self.assertIn("github.event_name == 'push'", each["if"])
                                self.assertIn("github.ref == 'refs/heads/main'", each["if"])

    def test_cargo_llvm_cov_is_a_pinned_release_binary(self) -> None:
        for name, job_name in CHECK_JOBS.items():
            with self.subTest(starter=name):
                found = step(starter(name)["jobs"][job_name], "Install cargo-llvm-cov")
                self.assertEqual(found["uses"], "taiki-e/install-action@v2")
                self.assertEqual(found["with"], {"tool": "cargo-llvm-cov@0.9.1"})
                self.assertEqual(found["if"], RUST)
                self.assertNotRegex((TEMPLATES / name).read_text(), r"cargo b?install")

    def test_each_third_party_action_is_pinned_to_a_major_tag(self) -> None:
        for name in STARTERS:
            for job in starter(name)["jobs"].values():
                for each in job["steps"]:
                    if "uses" in each:
                        with self.subTest(starter=name, uses=each["uses"]):
                            self.assertRegex(each["uses"], r"^[\w.-]+/[\w./-]+@v[0-9]+$")


class ToolchainTests(unittest.TestCase):
    def test_no_step_names_a_channel_or_sets_a_variable_of_rust_per_run(self) -> None:
        for name in STARTERS:
            text = (TEMPLATES / name).read_text()
            data = starter(name)
            with self.subTest(starter=name):
                # The only install of a toolchain takes no name, and no step picks one in another way.
                rustup = [line for line in runs(data) if re.match(r"rustup\b", line)]
                self.assertIn("rustup toolchain install", rustup)
                for line in rustup:
                    self.assertNotRegex(line, r"toolchain install \S|\b(default|override|run)\b|\b(stable|beta|nightly)\b")
                self.assertNotRegex(text, r"\+(stable|beta|nightly|[0-9])")
                for job in data["jobs"].values():
                    for each in job["steps"]:
                        self.assertNotIn("toolchain", each.get("with") or {})
                self.assertEqual(rust_variables(data), [])

    def test_the_scan_finds_a_variable_of_rust_per_run(self) -> None:
        probes = [{"env": {"CARGO_BUILD_ID": "${{ github.run_id }}"}, "jobs": {}},
                  {"jobs": {"j": {"env": {"RUSTFLAGS": "--cfg r${{ github.run_number }}"}, "steps": []}}},
                  {"jobs": {"j": {"steps": [{"env": {"RUSTUP_TOOLCHAIN": "stable"}}]}}},
                  {"jobs": {"j": {"steps": [{"run": 'echo "CARGO_X=$(date)" >> "$GITHUB_ENV"'}]}}},
                  {"jobs": {"j": {"steps": [{"run": "export RUSTUP_TOOLCHAIN=stable"}]}}}]
        for probe in probes:
            with self.subTest(probe=probe):
                self.assertNotEqual(rust_variables(probe), [])

    def test_each_job_installs_the_toolchain_and_every_rust_step_is_conditional(self) -> None:
        for name in STARTERS:
            for job_name, job in starter(name)["jobs"].items():
                names = [each.get("name") for each in job["steps"]]
                with self.subTest(starter=name, job=job_name):
                    install = step(job, INSTALL)
                    self.assertEqual(install["id"], "rust")
                    # A project without a toolchain file, in any language, skips each Rust step.
                    self.assertEqual(install["if"], HAS_TOOLCHAIN)
                    for each in job["steps"][names.index(INSTALL) + 1:]:
                        label = (each.get("name") or "").lower()
                        if "rust" in label or "llvm-cov" in label:
                            self.assertTrue(each.get("if", "").startswith(RUST), each.get("name"))
                    # The steps are the same in each job.
                    self.assertEqual(install, step(starter("github-release.yml")["jobs"]["check"], INSTALL))


@unittest.skipUnless(sys.version_info >= (3, 11), "needs tomllib, Python 3.11 or later")
class ToolchainShellTests(unittest.TestCase):
    """Run the shell of the install step, as GitHub runs it: bash -e -o pipefail, with a fake rustup."""

    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="ci-starter-test-")
        self.addCleanup(scratch.cleanup)
        self.base = Path(scratch.name)
        self.project = self.base / "project"
        self.project.mkdir()
        self.tools = self.base / "tools"
        self.tools.mkdir()
        (self.tools / "python3").symlink_to(sys.executable)
        self.log = self.base / "rustup.log"
        (self.tools / "rustup").write_text(f'#!/bin/sh\necho "$*" >> "{self.log}"\nexit 0\n')
        (self.tools / "rustup").chmod(0o755)
        self.output = self.base / "output"
        self.install = step(starter("github-release.yml")["jobs"]["check"], INSTALL)["run"]

    def bash(self, **env: str) -> subprocess.CompletedProcess[str]:
        self.output.write_text("")
        full = {key: value for key, value in os.environ.items() if not key.startswith(("RUSTUP", "CARGO"))}
        full.update(PATH=f"{self.tools}{os.pathsep}{os.environ['PATH']}", GITHUB_OUTPUT=str(self.output), **env)
        return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", self.install],
                              cwd=self.project, capture_output=True, text=True, env=full)

    def test_an_exact_version_is_the_toolchain_with_no_warning(self) -> None:
        for channel in ("1.95.0", "nightly-2026-11-12", "beta-2026-11-01"):
            (self.project / "rust-toolchain.toml").write_text(f'[toolchain]\nchannel = "{channel}"\n')
            done = self.bash()
            with self.subTest(channel=channel):
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(self.output.read_text(), f"toolchain={channel}\n")
                self.assertNotIn("::warning::", done.stdout)
        # No name after install: rustup reads the toolchain file.
        calls = self.log.read_text().splitlines()
        self.assertEqual(calls[:2], ["toolchain install", "component add clippy rustfmt llvm-tools-preview"])

    def test_a_channel_that_moves_gets_a_warning(self) -> None:
        for channel in ("stable", "1.95", "nightly"):
            (self.project / "rust-toolchain.toml").write_text(f'[toolchain]\nchannel = "{channel}"\n')
            done = self.bash()
            with self.subTest(channel=channel):
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertIn(f"::warning::The toolchain file names the channel {channel}, which moves", done.stdout)
                self.assertEqual(self.output.read_text(), f"toolchain={channel}\n")

    def test_the_old_file_rust_toolchain_comes_first(self) -> None:
        (self.project / "rust-toolchain").write_text("1.94.0\n")
        done = self.bash()
        self.assertEqual(self.output.read_text(), "toolchain=1.94.0\n", done.stderr)
        (self.project / "rust-toolchain.toml").write_text('[toolchain]\nchannel = "1.95.0"\n')
        self.bash()
        self.assertEqual(self.output.read_text(), "toolchain=1.94.0\n")

    def test_a_channel_that_no_key_can_hold_fails(self) -> None:
        for text in ('[toolchain]\npath = "/opt/rust"\n', '[toolchain]\nchannel = "1.95.0 x"\n',
                     '[toolchain]\nchannel = "1.95.0\\nx"\n', '[toolchain]\nchannel = "a/b"\n'):
            (self.project / "rust-toolchain.toml").write_text(text)
            done = self.bash()
            with self.subTest(text=text):
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertIn("names no channel that a cache key can hold", done.stdout)
                self.assertEqual(self.output.read_text(), "")

    def test_rustup_toolchain_fails_without_its_value(self) -> None:
        (self.project / "rust-toolchain.toml").write_text('[toolchain]\nchannel = "1.95.0"\n')
        done = self.bash(RUSTUP_TOOLCHAIN="secret-stable")
        self.assertEqual(done.returncode, 1)
        self.assertIn("RUSTUP_TOOLCHAIN is set", done.stdout)
        self.assertNotIn("secret-stable", done.stdout + done.stderr)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
