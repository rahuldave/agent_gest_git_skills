"""Check the Rust steps of the CI starters of gsu: github-check.yml and github-release.yml.

The Rust steps run only in a project with a toolchain file, rust-toolchain.toml or rust-toolchain. They read the
toolchain from the file and name no channel, restore a cache of the build, and save it only on a push to main. The key
of the cache holds the compiler that rustc -V prints, the word check that each job of just check shares, the hash of
each Cargo.lock and the commit. A project with a Cargo.toml and no toolchain file fails with a message that names the
fix. A project in another language skips each Rust step. The tests parse the YAML with PyYAML, and run the shell of
the toolchain steps with bash, a fake rustup and rustc, and Python 3.11 or later, for tomllib.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / ".agents/skills/gsu/assets/templates"
STARTERS = ("github-check.yml", "github-release.yml")
# The job of each starter that runs the checks, and so has the cache.
CHECK_JOBS = {"github-check.yml": "ci", "github-release.yml": "check"}
INSTALL = "Install the Rust toolchain of rust-toolchain.toml"
STOP = "Stop a Rust project that has no toolchain file"
# The condition of the install, as in the docs-publish workflow of jnterfaces.
HAS_TOOLCHAIN = "hashFiles('rust-toolchain.toml', 'rust-toolchain') != ''"
NO_TOOLCHAIN = "hashFiles('Cargo.toml') != '' && hashFiles('rust-toolchain.toml', 'rust-toolchain') == ''"
PATHS = ["~/.cargo/registry/index", "~/.cargo/registry/cache", "~/.cargo/git/db", "target/"]
# The word check stands for the build of just check, so the jobs of a pull request and of main share the cache.
# Each level of the key holds the hash of the path dependencies, so no restore takes a build of other files of them.
# The image of runs-on, so no run restores a build of another image.
IMAGE = "ubuntu-26.04"
PREFIX = ("${{ runner.os }}-${{ runner.arch }}-" + IMAGE + "-rust-${{ steps.rust.outputs.toolchain }}-check-paths-"
          "${{ steps.path-deps.outputs.hash }}-")
LOCK = PREFIX + "${{ hashFiles('**/Cargo.lock') }}-"
KEY = LOCK + "${{ github.sha }}"
RUST = "steps.rust.outputs.toolchain != ''"
RESTORE_IF = f"{RUST} && steps.path-deps.outputs.hash != ''"
SAVE_IF = (f"{RUST} && github.event_name == 'push' && github.ref == 'refs/heads/main' && "
           "steps.path-deps.outputs.hash != '' && steps.rust-cache.outputs.cache-hit != 'true' && "
           "steps.path-deps-after.outputs.changed != 'true'")
# The actions of the starters, each pinned by the full SHA of the commit of its version.
CACHE_SHA = "0057852bfaa89a56745cba8c7296529d2fc39830"
RESTORE = f"actions/cache/restore@{CACHE_SHA}"
SAVE = f"actions/cache/save@{CACHE_SHA}"
PATH_DEPS = "Set the times of the path dependencies"
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
        self.assertEqual(save["uses"], SAVE)
        self.assertLess(names.index("Restore the Rust cache"), names.index("Check"))
        self.assertGreater(names.index("Save the Rust cache"), names.index("Check"))
        self.assertEqual(paths(save), PATHS)
        # The save writes the key of the restore, so a Cargo.lock that the build writes changes nothing.
        self.assertEqual(save["with"]["key"], "${{ steps.rust-cache.outputs.cache-primary-key }}")
        self.assertEqual(save["if"], SAVE_IF)

    def test_each_check_job_restores_with_the_shared_key(self) -> None:
        for name, job_name in CHECK_JOBS.items():
            with self.subTest(starter=name):
                job = starter(name)["jobs"][job_name]
                names = [each.get("name") or each.get("uses") for each in job["steps"]]
                restore = step(job, "Restore the Rust cache")
                self.assertEqual(restore["uses"], RESTORE)
                self.assertEqual(restore["id"], "rust-cache")
                self.assertEqual(restore["if"], RESTORE_IF)
                self.assertLess(names.index(INSTALL), names.index("Restore the Rust cache"))
                # The times are set before the restore, which needs the hash, and before any build.
                self.assertLess(names.index(PATH_DEPS), names.index("Restore the Rust cache"))
                self.assertEqual(paths(restore), PATHS)
                self.assertEqual(restore["with"]["key"], KEY)
                # The newest cache with the same Cargo.lock first, then the newest of the same compiler.
                self.assertEqual(restore["with"]["restore-keys"].strip().splitlines(), [LOCK, PREFIX])

    def test_the_key_has_its_parts_in_order(self) -> None:
        key = step(starter("github-check.yml")["jobs"]["ci"], "Restore the Rust cache")["with"]["key"]
        parts = re.findall(r"\$\{\{ ([^}]+) \}\}|-(check)-|-(ubuntu-[0-9]{2}\.[0-9]{2})-", key)
        self.assertEqual([expr or word or image for expr, word, image in parts],
                         ["runner.os", "runner.arch", IMAGE, "steps.rust.outputs.toolchain", "check",
                          "steps.path-deps.outputs.hash", "hashFiles('**/Cargo.lock')", "github.sha"])

    def test_the_image_of_the_key_is_the_image_of_each_job(self) -> None:
        # A cache that ubuntu-24.04 built has other system libraries, so a job on ubuntu-26.04 must not restore it.
        for name in STARTERS:
            for job_name, job in starter(name)["jobs"].items():
                with self.subTest(starter=name, job=job_name):
                    self.assertEqual(job["runs-on"], IMAGE)
                    for each in job["steps"]:
                        if each.get("uses", "").startswith("actions/cache/restore@"):
                            levels = [each["with"]["key"]] + each["with"]["restore-keys"].strip().splitlines()
                            for level in levels:
                                self.assertIn(f"-{IMAGE}-rust-", level)

    def test_each_level_of_the_key_holds_the_hash_of_the_path_dependencies(self) -> None:
        # A level without the hash could restore a build of other files of a path dependency, whose old times would
        # make cargo take it as up to date: a false pass.
        for name, job_name in CHECK_JOBS.items():
            restore = step(starter(name)["jobs"][job_name], "Restore the Rust cache")
            levels = [restore["with"]["key"]] + restore["with"]["restore-keys"].strip().splitlines()
            for level in levels:
                with self.subTest(starter=name, level=level):
                    self.assertTrue(level.startswith(PREFIX), level)

    def test_a_pull_request_and_main_share_the_key_with_no_name_of_a_job(self) -> None:
        # The job of check.yml is ci, and the job of release.yml is check: a key with github.job would part them.
        keys = set()
        for name, job_name in CHECK_JOBS.items():
            text = (TEMPLATES / name).read_text()
            with self.subTest(starter=name):
                self.assertNotIn("github.job", text)
                restore = step(starter(name)["jobs"][job_name], "Restore the Rust cache")
                keys.add((restore["with"]["key"], restore["with"]["restore-keys"]))
        self.assertEqual(len(keys), 1)

    def test_the_commit_is_only_in_the_key_and_never_in_a_variable(self) -> None:
        for name in STARTERS:
            data = starter(name)
            with self.subTest(starter=name):
                for job in data["jobs"].values():
                    for each in job["steps"]:
                        found = "github.sha" in yaml.safe_dump(each)
                        is_restore = each.get("name") == "Restore the Rust cache"
                        self.assertEqual(found, is_restore, each.get("name"))
                        if is_restore:
                            self.assertNotIn("github.sha", each["with"]["restore-keys"])
                            self.assertNotIn("env", each)

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
                            self.assertIn(each["uses"], (RESTORE, SAVE))
                            if each["uses"].startswith("actions/cache/save"):
                                self.assertIn("github.event_name == 'push'", each["if"])
                                self.assertIn("github.ref == 'refs/heads/main'", each["if"])

    def test_the_cache_keeps_the_whole_build_folder(self) -> None:
        # The new build layout of cargo writes target/debug/build/<pkg>/<hash>/out/, so a narrower path misses files.
        for name in STARTERS:
            for job in starter(name)["jobs"].values():
                for each in job["steps"]:
                    if each.get("uses", "").startswith("actions/cache"):
                        with self.subTest(starter=name, step=each.get("name")):
                            # No narrower path and no exclusion such as !target/debug/build.
                            self.assertEqual(paths(each), PATHS)
                            self.assertFalse([path for path in paths(each) if path.startswith("!")])

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
                    # A Rust project without one stops first, with the fix.
                    stop = step(job, STOP)
                    self.assertEqual(stop["if"], NO_TOOLCHAIN)
                    self.assertEqual(names.index(STOP) + 1, names.index(INSTALL))
                    self.assertEqual(stop, step(starter("github-release.yml")["jobs"]["check"], STOP))
                    for each in job["steps"][names.index(INSTALL) + 1:]:
                        label = (each.get("name") or "").lower()
                        if "rust" in label or "llvm-cov" in label:
                            self.assertTrue(each.get("if", "").startswith(RUST), each.get("name"))
                    # The steps are the same in each job.
                    self.assertEqual(install, step(starter("github-release.yml")["jobs"]["check"], INSTALL))


class ConditionTests(unittest.TestCase):
    """Evaluate the conditions of the toolchain steps as GitHub does: hashFiles gives '' when no file matches."""

    @staticmethod
    def runs_in(condition: str, files: set[str]) -> bool:
        def part(text: str) -> bool:
            match = re.fullmatch(r"hashFiles\(([^)]*)\) (==|!=) ''", text.strip())
            assert match, text
            names = re.findall(r"'([^']+)'", match.group(1))
            hit = any(name in files for name in names)
            return hit if match.group(2) == "!=" else not hit
        return all(part(each) for each in condition.split("&&"))

    def test_only_a_rust_project_with_no_toolchain_file_stops(self) -> None:
        cases = {
            frozenset(): (False, False),
            frozenset({"pyproject.toml"}): (False, False),
            frozenset({"Cargo.toml"}): (True, False),
            frozenset({"Cargo.toml", "rust-toolchain.toml"}): (False, True),
            frozenset({"Cargo.toml", "rust-toolchain"}): (False, True),
            # A toolchain file alone still installs, as before.
            frozenset({"rust-toolchain.toml"}): (False, True),
        }
        for name, job_name in CHECK_JOBS.items():
            job = starter(name)["jobs"][job_name]
            for files, (stops, installs) in cases.items():
                with self.subTest(starter=name, files=sorted(files)):
                    self.assertEqual(self.runs_in(step(job, STOP)["if"], files), stops)
                    self.assertEqual(self.runs_in(step(job, INSTALL)["if"], files), installs)

    def test_the_stop_fails_and_names_the_fix(self) -> None:
        run = step(starter("github-check.yml")["jobs"]["ci"], STOP)["run"]
        done = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", run],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 1)
        self.assertRegex(done.stdout, r"^::error::.*Cargo\.toml and no rust-toolchain\.toml")
        self.assertIn("Run just install, which writes rust-toolchain.toml", done.stdout)


@unittest.skipUnless(sys.version_info >= (3, 11), "needs tomllib, Python 3.11 or later")
class ToolchainShellTests(unittest.TestCase):
    """Run the shell of the install step, as GitHub runs it: bash -e -o pipefail, with a fake rustup and rustc."""

    RUSTC = "rustc 1.95.0 (59807616e 2026-04-14)"
    TOOLCHAIN = "1.95.0-59807616e-2026-04-14"

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
        # rustc -V prints the line of FAKE_RUSTC, as the rustc of the toolchain file would.
        (self.tools / "rustc").write_text('#!/bin/sh\n[ "$1" = -V ] || exit 2\nprintf \'%s\\n\' "$FAKE_RUSTC"\n')
        (self.tools / "rustc").chmod(0o755)
        self.output = self.base / "output"
        self.install = step(starter("github-release.yml")["jobs"]["check"], INSTALL)["run"]

    def bash(self, rustc: str = RUSTC, **env: str) -> subprocess.CompletedProcess[str]:
        self.output.write_text("")
        full = {key: value for key, value in os.environ.items() if not key.startswith(("RUSTUP", "CARGO"))}
        full.update(PATH=f"{self.tools}{os.pathsep}{os.environ['PATH']}", GITHUB_OUTPUT=str(self.output),
                    FAKE_RUSTC=rustc, **env)
        return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", self.install],
                              cwd=self.project, capture_output=True, text=True, env=full)

    def write(self, channel: str) -> None:
        (self.project / "rust-toolchain.toml").write_text(f'[toolchain]\nchannel = "{channel}"\n')

    def test_the_key_holds_the_version_that_rustc_prints(self) -> None:
        for channel in ("1.95.0", "nightly-2026-11-12", "beta-2026-11-01"):
            self.write(channel)
            done = self.bash()
            with self.subTest(channel=channel):
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(self.output.read_text(), f"toolchain={self.TOOLCHAIN}\n")
                self.assertNotIn("::warning::", done.stdout)
        # No name after install: rustup reads the toolchain file.
        calls = self.log.read_text().splitlines()
        self.assertEqual(calls[:2], ["toolchain install", "component add clippy rustfmt llvm-tools-preview"])

    def test_a_nightly_keeps_its_commit_and_date(self) -> None:
        self.write("nightly-2026-11-12")
        self.bash(rustc="rustc 1.97.0-nightly (abc123def 2026-11-11)")
        self.assertEqual(self.output.read_text(), "toolchain=1.97.0-nightly-abc123def-2026-11-11\n")

    def test_a_channel_that_moves_gets_a_new_key_with_each_compiler(self) -> None:
        self.write("stable")
        keys = []
        for rustc in ("rustc 1.95.0 (59807616e 2026-04-14)", "rustc 1.96.0 (aaaaaaaaa 2026-05-26)"):
            done = self.bash(rustc=rustc)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("::warning::The toolchain file names no exact version (stable)", done.stdout)
            keys.append(self.output.read_text())
        self.assertEqual(keys, ["toolchain=1.95.0-59807616e-2026-04-14\n", "toolchain=1.96.0-aaaaaaaaa-2026-05-26\n"])

    def test_each_channel_that_moves_gets_a_warning(self) -> None:
        for channel in ("stable", "1.95", "nightly"):
            self.write(channel)
            done = self.bash()
            with self.subTest(channel=channel):
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertIn(f"::warning::The toolchain file names no exact version ({channel})", done.stdout)
                self.assertEqual(self.output.read_text(), f"toolchain={self.TOOLCHAIN}\n")

    def test_the_old_file_rust_toolchain_comes_first(self) -> None:
        (self.project / "rust-toolchain").write_text("stable\n")
        self.write("1.95.0")
        self.assertIn("no exact version (stable)", self.bash().stdout)
        (self.project / "rust-toolchain").write_text("1.94.0\n")
        self.write("stable")
        self.assertNotIn("::warning::", self.bash().stdout)

    def test_a_file_with_no_plain_channel_warns_without_its_text(self) -> None:
        # The key comes from rustc, not from the file. The warning never prints the text of the file, so a line of it
        # cannot become a command of the workflow. (A real rustup cannot install a toolchain of path, so such a
        # project fails at rustup toolchain install; the fake here only shows that the warning stays clean.)
        for text in ('[toolchain]\npath = "/opt/rust"\n', '[toolchain]\nchannel = "1.95.0 x"\n',
                     '[toolchain]\nchannel = "1.95.0\\n::error::x"\n', '[toolchain]\nchannel = "a/b"\n'):
            (self.project / "rust-toolchain.toml").write_text(text)
            done = self.bash()
            with self.subTest(text=text):
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertIn("::warning::The toolchain file names no exact version (no channel)", done.stdout)
                self.assertNotIn("::error::", done.stdout)
                self.assertEqual(self.output.read_text(), f"toolchain={self.TOOLCHAIN}\n")

    def test_an_exact_version_with_a_host_triple_gets_no_warning(self) -> None:
        for channel in ("1.95.0-x86_64-unknown-linux-gnu", "1.95.0-aarch64-apple-darwin",
                        "nightly-2026-11-12-x86_64-unknown-linux-gnu"):
            self.write(channel)
            done = self.bash()
            with self.subTest(channel=channel):
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertNotIn("::warning::", done.stdout)
        self.write("stable-x86_64-unknown-linux-gnu")
        self.assertIn("::warning::", self.bash().stdout)

    def test_a_failed_read_of_the_channel_only_warns(self) -> None:
        # An old python3 without tomllib, or a file that is not UTF-8, must not stop the step.
        self.write("1.95.0")
        (self.tools / "python3").unlink()
        (self.tools / "python3").write_text("#!/bin/sh\necho 'ModuleNotFoundError: tomllib' >&2\nexit 1\n")
        (self.tools / "python3").chmod(0o755)
        done = self.bash()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("::warning::The toolchain file names no exact version (no channel)", done.stdout)
        self.assertEqual(self.output.read_text(), f"toolchain={self.TOOLCHAIN}\n")

    def test_a_rustc_with_no_version_fails(self) -> None:
        self.write("1.95.0")
        for rustc in ("", "rustc", "error: no toolchain", "rustc 1.95 (x)"):
            done = self.bash(rustc=rustc)
            with self.subTest(rustc=rustc):
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertIn("::error::rustc -V printed no version of Rust", done.stdout)
                self.assertEqual(self.output.read_text(), "")

    def test_rustup_toolchain_fails_without_its_value(self) -> None:
        self.write("1.95.0")
        done = self.bash(RUSTUP_TOOLCHAIN="secret-stable")
        self.assertEqual(done.returncode, 1)
        self.assertIn("RUSTUP_TOOLCHAIN is set", done.stdout)
        self.assertNotIn("secret-stable", done.stdout + done.stderr)
        self.assertFalse(self.log.exists())


INSTALL_TOOLS = "Install the pinned tools"
TARGETS = ("x86_64-unknown-linux-musl", "aarch64-unknown-linux-musl")
FETCH = re.compile(r'^\s*fetch\s+"?([^"\s]+)"?\s+"?([^"\s]+)"?\s*$')
PIN_LINE = re.compile(r"^([0-9a-f]{64})  (\S+)$")


# --- The scan of the missing pins. Keep it the same as in tests/test_workflow_pins.py of jnterfaces. ---
# uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
# The key may be quoted, and the step may be a flow mapping: {uses: a/b@SHA} # v1.2.3.
USES = re.compile(r"""(?:^|[\s{,\-])["']?uses["']?\s*:\s*["']?([^\s"'{}\[\],]+)["']?\s*[}\],]*\s*(.*)$""")
SHA_PIN = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
# An action of the repository itself, or an image pinned by its digest, needs no SHA of a commit and no note.
LOCAL_OR_IMAGE = re.compile(r"^(?:\./\S+|docker://\S+@sha256:[0-9a-f]{64})$")
VERSION_NOTE = re.compile(r"^\s*# v[0-9]+\.[0-9]+\.[0-9]+\s*$")
EXACT = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
# The runner image of a job, by an exact version, such as ubuntu-26.04. ubuntu-latest moves to a new image.
RUNNER = re.compile(r"^ubuntu-[0-9]{2}\.[0-9]{2}$")
# A download of a release of just or uv. The version after download/ must be exact.
RELEASE = re.compile(r"github\.com/(casey/just|astral-sh/uv)/releases/(?:download/([^/\s\"']+)|latest)")
SHELLS = r"(?:(?:ba|z|da|k)?sh|python3?|perl|ruby)"
# A shell that reads its script from stdin: a shell, or python, perl or ruby with no script or code of its own.
STDIN_SHELL = (r"(?:(?:ba|z|da|k)?sh\b|(?:python3?|perl|ruby)(?:\s+-(?![cmeE]\b)[A-Za-z]+)*"
               r"(?:\s+-(?=\s|$)|\s*(?:$|[;&|)])))")
# A shell at any stage after a pipe, also by its path, through env or sudo, as after tee or gunzip.
PIPE_SHELL = (r"\|\s*(?:[^|]*\|\s*)*(?:sudo\s+(?:-\S+\s+)*)?(?:env\s+(?:-\S+\s+|\w+=\S*\s+)*)?(?:/\S*/)?"
              + STDIN_SHELL)
# A script that a download pipes into a shell, that a shell runs from $(...) or <(...), and an install of just or uv
# with pip, pipx, cargo or brew. No pin checks any of them.
PIPED = re.compile(r"\b(?:curl|wget)\b[^|]*" + PIPE_SHELL + r"|"
                   r"\b(?:" + SHELLS + r"\s+-c|eval)\s+[\"']?(?:\$\(|`)\s*(?:curl|wget)\b|"
                   r"<\(\s*(?:curl|wget)\b|"
                   r"\b(?:pipx|pip3?|uv\s+pip|uv\s+tool|cargo)\s+(?:b?install)\s+(?:-\S+\s+)*(?:rust-just|uv|just)(?![\w.-])|"
                   r"\b(?:apt-get|apt|snap)\s+install\b.*\b(?:just|uv)\b")
# An install with brew, and a download with gh, which no pin checks.
BREW = re.compile(r"\bbrew\s+(?:install|reinstall|upgrade|bundle)\b|\bgh\s+release\s+download\b")
DOWNLOAD = re.compile(r"\b(curl|wget)\b([^|;&\n]*)")
# A run of a file by a shell, source, exec, ., or by its path.
RUN_BY = r"(?:(?:sudo\s+)?(?:" + SHELLS + r"|source|exec|\.)\s+(?:-\S+\s+)*(?:<\s*)?[\"']?[^\s\"']*|\./[^\s\"']*|chmod\s+\S+\s+[\"']?[^\s\"']*)"


def downloaded_files(args: str, tool: str) -> list[str]:
    """The name of each file that a curl or wget with the words ARGS writes, without its folder."""
    try:
        words = shlex.split(args, comments=False)
    except ValueError:
        words = args.split()
    names, urls, saved = [], [w for w in words if re.match(r"^[a-z]+://", w)], False
    for index, word in enumerate(words):
        value = None
        if word in ("-o", "--output", "--output-document") or (tool == "wget" and word == "-O"):
            value = words[index + 1] if index + 1 < len(words) else None
        elif word.startswith(("--output=", "--output-document=")):
            value = word.split("=", 1)[1]
        elif tool == "curl" and re.match(r"^-[A-Za-z]*o$", word):
            value = words[index + 1] if index + 1 < len(words) else None
        elif tool == "curl" and re.match(r"^-[A-Za-z]*o.+", word):
            value = word[word.index("o") + 1:]
        elif tool == "wget" and re.match(r"^-[A-Za-z]*O.+", word):
            value = word[word.index("O") + 1:]
        elif re.fullmatch(r"[12]?>>?", word):
            value = words[index + 1] if index + 1 < len(words) else None
        elif re.match(r"^[12]?>", word):
            value = re.sub(r"^[12]?>+", "", word)
        elif tool == "wget" and re.match(r"^-[A-Za-z]*O$", word):
            value = words[index + 1] if index + 1 < len(words) else None
        elif tool == "curl" and (word in ("-O", "--remote-name") or re.match(r"^-[A-Za-z]*O[A-Za-z]*$", word)):
            names += [url.rstrip("/").rsplit("/", 1)[-1] for url in urls]
            saved = True
        if value:
            saved = True
            if value != "-":
                names.append(value.rstrip("/").rsplit("/", 1)[-1])
    if tool == "wget" and not saved:
        names += [url.rstrip("/").rsplit("/", 1)[-1] for url in urls]
    return [name for name in names if name]


def pin_findings(text: str) -> list[str]:
    """The missing pins of the workflow TEXT: an action, also in a note, not pinned by the full SHA of a commit with
    its version in a note after it; a setup of just or uv with no exact version; a download of a release of just or
    uv with no exact version; a script that a download pipes into a shell, or that a shell runs from $(...) or <(...);
    a file that curl or wget writes and a later line runs; and an install with brew. No pin checks these."""
    findings = []
    data = yaml.safe_load(text) or {}
    steps = [each for job in (data.get("jobs") or {}).values() for each in job.get("steps") or []]
    findings += lines_findings(text.splitlines(), "line")
    # The run of each step as the shell gets it, so a quoted YAML string with \\n cannot hide a line.
    for index, each in enumerate(steps, 1):
        findings += lines_findings(str(each.get("run") or "").splitlines(), f"step {index}, line")
    # Each uses of a step or of a job as YAML reads it, so no spelling of the key can hide an action.
    jobs = [job for job in (data.get("jobs") or {}).values() if isinstance(job, dict)]
    for name, job in (data.get("jobs") or {}).items():
        if isinstance(job, dict) and "uses" not in job and not RUNNER.match(str(job.get("runs-on", ""))):
            findings.append(f"job {name}: runs-on {job.get('runs-on')!r} is not an exact image such as ubuntu-26.04")
    for each in steps + jobs:
        uses = str(each.get("uses") or "")
        if uses and not (SHA_PIN.match(uses) or LOCAL_OR_IMAGE.match(uses)):
            findings.append(f"{uses} is not pinned by the full SHA of a commit")
    for each in steps:
        uses, given = each.get("uses") or "", each.get("with") or {}
        if uses.startswith("extractions/setup-just@") and not EXACT.match(str(given.get("just-version", ""))):
            findings.append(f"{uses}: no exact just-version")
        if uses.startswith("astral-sh/setup-uv@") and not EXACT.match(str(given.get("version", ""))):
            findings.append(f"{uses}: no exact version of uv")
    return findings


def lines_findings(lines: list[str], where: str) -> list[str]:
    """The missing pins of LINES, each named as WHERE and its number."""
    findings = []
    # A line that ends in a backslash goes on with the next line, as the shell reads it.
    joined, start = [], None
    for line in lines:
        if start is not None:
            joined[start] = joined[start][:-1] + " " + line.strip()
            joined.append("")
        else:
            start = len(joined)
            joined.append(line)
        if not joined[start].endswith("\\"):
            start = None
    lines = joined
    for number, line in enumerate(lines, 1):
        match = USES.search(line)
        if match and not LOCAL_OR_IMAGE.match(match.group(1)):
            if not SHA_PIN.match(match.group(1)):
                findings.append(f"{where} {number}: {match.group(1)} is not pinned by the full SHA of a commit")
            if not VERSION_NOTE.match(match.group(2)):
                findings.append(f"{where} {number}: {match.group(1)} has no note # vX.Y.Z with its version")
        for repo, version in RELEASE.findall(line):
            if not EXACT.match(version):
                findings.append(f"{where} {number}: a download of {repo} with no exact version")
        if PIPED.search(line):
            findings.append(f"{where} {number}: a shell runs a downloaded script, and no pin checks it")
        if BREW.search(line):
            findings.append(f"{where} {number}: brew installs a tool, and no pin checks it")
        for download in DOWNLOAD.finditer(line):
            for name in downloaded_files(download.group(2), download.group(1)):
                if name.startswith("$"):
                    continue
                later = "\n".join([line[download.end():]] + lines[number:])
                if re.search(RUN_BY + re.escape(name) + r"(?![\w.-])", later):
                    findings.append(f"{where} {number}: a later line runs {name}, which a download wrote and no pin checks")
    return findings
# --- The end of the scan. ---


def without_runner(findings: list[str]) -> list[str]:
    """The findings of a probe with no runs-on, without the one about runs-on."""
    return [finding for finding in findings if "runs-on" not in finding]


def install_run(name: str = "github-check.yml", job: str | None = None) -> str:
    return step(starter(name)["jobs"][job or CHECK_JOBS[name]], INSTALL_TOOLS)["run"]


def pinned(run: str) -> dict[str, str]:
    """The pins of the install step: the name of each download and its SHA-256."""
    block = run.split("pins='", 1)[1].split("'", 1)[0]
    found = {}
    for line in filter(None, (line.strip() for line in block.splitlines())):
        match = PIN_LINE.match(line)
        assert match, f"not a pin: {line}"
        assert match.group(2) not in found, f"two pins for {match.group(2)}"
        found[match.group(2)] = match.group(1)
    return found


def fetches(run: str) -> list[tuple[str, str]]:
    """The name and the URL of each fetch of the install step."""
    return [FETCH.match(line).groups() for line in run.splitlines() if FETCH.match(line)]


class PinTests(unittest.TestCase):
    def test_each_action_is_pinned_by_the_full_sha_of_a_commit_with_its_version(self) -> None:
        for name in STARTERS:
            with self.subTest(starter=name):
                self.assertEqual(pin_findings((TEMPLATES / name).read_text()), [])

    def test_the_scan_finds_each_missing_pin(self) -> None:
        sha = "11d5960a326750d5838078e36cf38b85af677262"
        probes = [
            "jobs: {j: {steps: [{uses: actions/checkout@v4}]}}",
            f"jobs: {{j: {{steps: [{{uses: actions/checkout@{sha[:12]}}}]}}}}",
            f"jobs:\n  j:\n    steps:\n      - uses: actions/checkout@{sha}\n",
            f"jobs:\n  j:\n    steps:\n      - uses: actions/checkout@{sha} # v4\n",
            "#   - uses: actions/checkout@v4\njobs: {}\n",
            f"jobs:\n  j:\n    steps:\n      - uses: extractions/setup-just@{sha} # v3.1.0\n",
            f"jobs:\n  j:\n    steps:\n      - uses: extractions/setup-just@{sha} # v3.1.0\n"
            "        with: {just-version: '1'}\n",
            f"jobs:\n  j:\n    steps:\n      - uses: astral-sh/setup-uv@{sha} # v6.8.0\n        with: {{version: latest}}\n",
            "jobs: {j: {steps: [{run: 'curl -fsSL https://astral.sh/uv/install.sh | sh'}]}}",
            "jobs: {j: {steps: [{run: 'curl -fsSL https://github.com/astral-sh/uv/releases/latest/download/uv.tar.gz'}]}}",
            "jobs: {j: {steps: [{run: 'curl -O https://github.com/casey/just/releases/download/$V/just.tar.gz'}]}}",
            "jobs: {j: {steps: [{run: 'wget -qO- https://astral.sh/uv/install.sh | sh'}]}}",
            "jobs: {j: {steps: [{run: 'sh -c \"$(curl -fsSL https://just.systems/install.sh)\"'}]}}",
            "jobs: {j: {steps: [{run: 'pipx install uv'}]}}",
            "jobs: {j: {steps: [{run: 'cargo install --locked just'}]}}",
            # The forms that the review of v0.10.0 found: a saved script that a later line runs, <(...), wget | sh
            # and brew.
            "jobs: {j: {steps: [{run: 'wget -O - https://x.example/i.sh | sudo -E bash'}]}}",
            "jobs: {j: {steps: [{run: 'bash -c \"$(wget -qO- https://x.example/i.sh)\"'}]}}",
            "jobs: {j: {steps: [{run: 'eval \"$(curl -fsSL https://x.example/env)\"'}]}}",
            "jobs: {j: {steps: [{run: 'bash <(curl -fsSL https://x.example/i.sh)'}]}}",
            "jobs: {j: {steps: [{run: 'source <(wget -qO- https://x.example/i.sh)'}]}}",
            "jobs: {j: {steps: [{run: 'curl -fsSL -o i.sh https://x.example/install.sh && sh i.sh'}]}}",
            "jobs: {j: {steps: [{run: 'curl -fsSLo i.sh https://x.example/install.sh; bash ./i.sh'}]}}",
            "jobs: {j: {steps: [{run: 'curl --output=/tmp/i.sh https://x.example/install.sh && sh /tmp/i.sh'}]}}",
            "jobs: {j: {steps: [{run: \"curl -fsSL -o \\\"$RUNNER_TEMP/i.sh\\\" https://x.example/a\\nsh \\\"$RUNNER_TEMP/i.sh\\\"\"}]}}",
            "jobs: {j: {steps: [{run: 'curl -fsSLO https://x.example/install.sh\nchmod +x install.sh\n./install.sh'}]}}",
            "jobs: {j: {steps: [{run: 'wget https://x.example/install.sh && sh install.sh'}]}}",
            "jobs: {j: {steps: [{run: 'wget -O i.sh https://x.example/a && . ./i.sh'}]}}",
            "jobs: {j: {steps: [{run: 'brew install just uv'}]}}",
            # The forms that the first review of this scan found.
            'jobs:\n  j:\n    steps:\n      - "uses": actions/checkout@main\n',
            'jobs:\n  j:\n    steps:\n      - uses : actions/checkout@v4\n',
            'jobs:\n  j:\n    uses: o/r/.github/workflows/w.yml@main\n',
            "jobs: {j: {steps: [{run: 'curl -fsSL https://x.example/i.sh | tee i.sh | sh'}]}}",
            "jobs: {j: {steps: [{run: 'curl -fsSL https://x.example/i.sh | /bin/bash'}]}}",
            "jobs: {j: {steps: [{run: 'curl -fsSL https://x.example/i.sh | env bash'}]}}",
            "jobs: {j: {steps: [{run: 'curl -fsSL https://x.example/i.sh > i.sh && sh i.sh'}]}}",
            "jobs: {j: {steps: [{run: 'curl -fsSL https://x.example/i.sh \\\n  | sh'}]}}",
            "jobs: {j: {steps: [{run: 'pip install rust-just'}]}}",
            "jobs: {j: {steps: [{run: 'cargo install -y just'}]}}",
            "jobs: {j: {steps: [{run: 'gh release download v1 -R casey/just'}]}}",
            "jobs: {j: {steps: [{run: 'sudo apt-get install -y just'}]}}",
            # The forms that the second review found.
            "jobs: {j: {steps: [{run: 'wget -qO i.sh https://x.example/a && sh i.sh'}]}}",
            "jobs: {j: {steps: [{run: 'curl -fsSL https://x.example/a.gz | gunzip | sh'}]}}",
            "jobs: {j: {steps: [{run: 'sh -c \"`curl -fsSL https://x.example/a`\"'}]}}",
            "jobs: {j: {steps: [{run: 'curl -fsSL https://x.example/a 1>i.sh && sh i.sh'}]}}",
            "jobs: {j: {steps: [{run: 'curl -fsSL https://x.example/a | python3'}]}}",
            "jobs: {j: {steps: [{run: 'curl -fsSL https://x.example/a | python3 -'}]}}",
            # The forms that the third review found.
            "jobs: {j: {steps: [{run: 'curl -fsSL \\\n  https://x.example/i.sh \\\n  | sh'}]}}",
            "jobs: {j: {steps: [{run: 'curl -fsSL https://x.example/a | python3 - --version 1.8'}]}}",
            "jobs: {j: {steps: [{run: 'curl -fsSL https://x.example/a | python3 -I'}]}}",
            "jobs: {j: {steps: [{run: 'curl -fsSL https://x.example/a | perl -w'}]}}",
            "jobs: {j: {steps: [{run: 'curl -fsSL -o i.sh https://x.example/a\nsh < i.sh'}]}}",
            "jobs: {j: {steps: [{run: 'curl -fsSL -o i.sh https://x.example/a\nbash -s < i.sh'}]}}",
        ]
        for probe in probes:
            with self.subTest(probe=probe):
                self.assertNotEqual(without_runner(pin_findings(probe)), [])
        for runner in ("", "runs-on: ubuntu-latest", "runs-on: ubuntu-24", "runs-on: [self-hosted, linux]",
                       "runs-on: ${{ matrix.os }}", "runs-on: macos-15"):
            with self.subTest(runner=runner):
                self.assertNotEqual(pin_findings(f"jobs:\n  j:\n    {runner}\n    steps: []\n"), [])
        self.assertEqual(pin_findings("jobs:\n  j:\n    runs-on: ubuntu-26.04\n    steps: []\n"), [])
        good = (f"jobs:\n  j:\n    steps:\n      - uses: astral-sh/setup-uv@{sha} # v6.8.0\n"
                "        with: {version: 0.13.7}\n"
                "      - run: curl -O https://github.com/casey/just/releases/download/1.59.0/just.tar.gz\n")
        self.assertEqual(without_runner(pin_findings(good)), [])
        # An action of the repository, an image by its digest, a quoted value and a flow step are pinned forms.
        fine = (f"jobs:\n  j:\n    steps:\n      - uses: ./.github/actions/x\n"
                f"      - uses: docker://alpine@sha256:{'a' * 64}\n"
                f"      - uses: 'actions/checkout@{sha}' # v4.4.0\n"
                f"      - {{uses: actions/checkout@{sha}}} # v4.4.0\n")
        self.assertEqual(without_runner(pin_findings(fine)), [])
        # python that runs its own code reads the download as data.
        self.assertEqual(without_runner(pin_findings(
            "jobs: {j: {steps: [{run: 'curl -fsSL https://x.example/a | python3 -c pass'}]}}")), [])
        # A package whose name starts with uv- or just- is not uv or just.
        package = "jobs: {j: {steps: [{run: 'pip install uv-dynamic-versioning'}]}}"
        self.assertEqual(without_runner(pin_findings(package)), [])

    def test_no_action_installs_a_tool(self) -> None:
        # The step that installs the tools checks each download against a pin in the file. An action that installs
        # a tool would check it against the server of the tool, or not at all.
        for name in STARTERS:
            actions = {each["uses"].split("@")[0] for job in starter(name)["jobs"].values() for each in job["steps"]
                       if "uses" in each}
            with self.subTest(starter=name):
                self.assertLessEqual(actions, {"actions/checkout", "actions/cache/restore", "actions/cache/save"})

    def test_each_job_installs_the_pinned_tools_with_one_step(self) -> None:
        run = install_run()
        for name in STARTERS:
            for job_name, job in starter(name)["jobs"].items():
                names = [each.get("name") for each in job["steps"]]
                with self.subTest(starter=name, job=job_name):
                    found = step(job, INSTALL_TOOLS)
                    self.assertEqual(found["run"], run)
                    self.assertEqual(found["shell"], "bash")
                    self.assertNotIn("if", found)
                    # Before each step that runs just.
                    first_just = min(index for index, each in enumerate(job["steps"])
                                     if re.search(r"^\s*just\s", each.get("run") or "", re.M))
                    self.assertLess(names.index(INSTALL_TOOLS), first_just)
                    # Only a job that runs cargo in its checks installs the tools of Rust.
                    env = found.get("env") or {}
                    if job_name == CHECK_JOBS.get(name):
                        self.assertEqual(env, {"JN_RUST_TOOLS": "${{ steps.rust.outputs.toolchain != '' && '1' || '' }}"})
                        self.assertGreater(names.index(INSTALL_TOOLS), names.index(INSTALL))
                    else:
                        self.assertEqual(env, {})

    def test_the_release_job_installs_jlog_before_just_release(self) -> None:
        # The recipes run their steps through jlog, so the job release needs it as the job check does.
        job = starter("github-release.yml")["jobs"]["release"]
        names = [each.get("name") for each in job["steps"]]
        self.assertLess(names.index(INSTALL_TOOLS), names.index("Release"))
        self.assertIn("jlog-v0.5.0-$target.tar.gz", [name for name, _ in fetches(step(job, INSTALL_TOOLS)["run"])])

    def test_each_download_has_a_pin_for_each_machine_and_names_its_version(self) -> None:
        run = install_run()
        pins = pinned(run)
        used = set()
        self.assertTrue(fetches(run))
        for name, url in fetches(run):
            for target in TARGETS:
                file = name.replace("$target", target)
                link = url.replace("$target", target)
                with self.subTest(file=file):
                    self.assertIn(file, pins)
                    used.add(file)
                    self.assertNotIn("$", link)
                    self.assertTrue(link.startswith("https://"))
                    version = re.match(r"^[a-z-]+?-(v?[0-9]+\.[0-9]+\.[0-9]+)-", file).group(1)
                    if file.endswith("install.sh"):
                        # The script comes from the full SHA of the commit of its tag, not from the tag.
                        self.assertRegex(link, r"^https://raw\.githubusercontent\.com/rahuldave/jlog/[0-9a-f]{40}/")
                    else:
                        self.assertRegex(link, rf"/download/(v|cargo-nextest-)?{re.escape(version.lstrip('v'))}/")
        # No pin is left over.
        self.assertEqual(set(pins), used)

    def test_just_and_uv_have_exact_versions(self) -> None:
        names = [name for name, _ in fetches(install_run())]
        for tool in ("just", "uv"):
            with self.subTest(tool=tool):
                [found] = [name for name in names if name.startswith(tool + "-")]
                self.assertRegex(found, rf"^{tool}-[0-9]+\.[0-9]+\.[0-9]+-\$target\.tar\.gz$")

    def test_the_tools_of_rust_keep_the_versions_of_jnprofile_rust(self) -> None:
        names = [name for name, _ in fetches(install_run())]
        self.assertIn("cargo-llvm-cov-0.9.1-$target.tar.gz", names)
        self.assertIn("cargo-nextest-0.9.151-$target.tar.gz", names)

    @unittest.skipUnless(os.environ.get("JN_TEST_NETWORK") == "1", "set JN_TEST_NETWORK=1 to read each tag")
    def test_each_action_sha_is_the_commit_of_its_tag(self) -> None:
        for path in [TEMPLATES / name for name in STARTERS] + [ROOT / ".github/workflows/verify.yml"]:
            for line in path.read_text().splitlines():
                match = USES.search(line)
                if not match:
                    continue
                action, sha = match.group(1).split("@")
                tag = match.group(2).split("#", 1)[1].strip()
                repo = "/".join(action.split("/")[:2])
                refs = subprocess.run(["git", "ls-remote", f"https://github.com/{repo}", f"refs/tags/{tag}",
                                       f"refs/tags/{tag}^{{}}"], capture_output=True, text=True, check=True).stdout
                found = dict(reversed(line.split("\t")) for line in refs.splitlines())
                with self.subTest(action=action, tag=tag):
                    # An annotated tag points at a tag object; the commit is the line of ^{}.
                    self.assertEqual(found.get(f"refs/tags/{tag}^{{}}", found.get(f"refs/tags/{tag}")), sha)

    @unittest.skipUnless(os.environ.get("JN_TEST_NETWORK") == "1", "set JN_TEST_NETWORK=1 to download each pin")
    def test_each_pin_is_the_sha256_of_its_download(self) -> None:
        import hashlib
        import urllib.request
        # Each download of each install step of the starters and of verify.yml, once.
        seen = set()
        for place, run in own_steps().items():
            pins = pinned(run)
            for name, url in fetches(run):
                for file, link in files_of(name, url):
                    if file in seen:
                        continue
                    seen.add(file)
                    with self.subTest(place=place, file=file), urllib.request.urlopen(link, timeout=60) as response:
                        self.assertEqual(hashlib.sha256(response.read()).hexdigest(), pins[file])



VERIFY = ROOT / ".github/workflows/verify.yml"
# The tools that each job of verify.yml installs, and no other.
VERIFY_TOOLS = {"verify": {"just", "uv", "jlog", "gest", "jagt", "smalldocs"}, "release": {"just", "uv"},
                "docs": {"just", "uv", "smalldocs"}}
# The tool and the version in the name of a download, such as just-1.59.0-$target.tar.gz or
# smalldocs-0.5.13-py3-none-any.whl.
TOOL_NAME = re.compile(r"^([a-z-]+?)-v?([0-9]+\.[0-9]+\.[0-9]+)-")
# The one curl of each install step, in the function fetch, which checks the SHA-256 of each download.
FETCH_CURL = 'curl -fsSL --retry 3 -o "$work/$1" "$2"'
# The workflows of jnterfaces that pin the same tools.
JNTERFACES_WORKFLOWS = (".github/workflows/verify.yml", ".agents/skills/docs/assets/docs-publish.yml")


def files_of(name: str, url: str) -> list[tuple[str, str]]:
    """Each file and link of a fetch: one for each machine, or one when the name has no $target."""
    if "$target" not in name + url:
        return [(name, url)]
    return [(name.replace("$target", target), url.replace("$target", target)) for target in TARGETS]


def install_steps(data: dict) -> dict[str, str]:
    """The run of the step that installs the pinned tools, for each job of the workflow DATA that has one."""
    found = {}
    for job_name, job in (data.get("jobs") or {}).items():
        runs = [each["run"] for each in job.get("steps") or [] if each.get("name") == INSTALL_TOOLS]
        assert len(runs) <= 1, job_name
        if runs:
            found[job_name] = runs[0]
    return found


def own_steps() -> dict[str, str]:
    """The run of each install step of this repository, by the file and the job."""
    found = {}
    for name in STARTERS:
        found |= {f"{name} {job}": run for job, run in install_steps(starter(name)).items()}
    found |= {f"verify.yml {job}": run for job, run in install_steps(yaml.safe_load(VERIFY.read_text())).items()}
    return found


def jnterfaces_folder(file: str) -> Path:
    """The jnterfaces clone that the checks use, which must have FILE. A clone that is too old fails with the message
    of find_jnterfaces.sh, which names each folder that it tried."""
    found = subprocess.run(["bash", str(ROOT / "scripts/find_jnterfaces.sh"), file], capture_output=True, text=True)
    if found.returncode != 0:
        raise AssertionError(f"{found.stderr.strip()} The commit of scripts/jnterfaces_commit has it, so set "
                             "JNTERFACES_DIR to a clone of that commit, or update your clone.")
    return Path(found.stdout.strip())


def jnterfaces_steps() -> dict[str, str]:
    """The run of each install step of the workflows of the jnterfaces clone that the checks use."""
    folder = jnterfaces_folder(JNTERFACES_WORKFLOWS[1])
    found = {}
    for name in JNTERFACES_WORKFLOWS:
        data = yaml.safe_load((Path(folder) / name).read_text())
        found |= {f"jnterfaces {name} {job}": run for job, run in install_steps(data).items()}
    return found


def drift(steps: dict[str, str]) -> list[str]:
    """Each download with two SHA-256 values, and each tool with two versions, in the install STEPS."""
    digests, versions = {}, {}
    for place, run in steps.items():
        for name, digest in pinned(run).items():
            digests.setdefault(name, {})[digest] = place
            tool, version = TOOL_NAME.match(name).groups()
            versions.setdefault(tool, {})[version] = place
    return ([f"{name}: {places}" for name, places in digests.items() if len(places) > 1] +
            [f"{tool}: {places}" for tool, places in versions.items() if len(places) > 1])


class VerifyPinTests(unittest.TestCase):
    """verify.yml pins its tools as the starters do: the same step, the same versions and the same SHA-256 values."""

    def setUp(self) -> None:
        self.data = yaml.safe_load(VERIFY.read_text())

    def test_verify_yml_has_no_missing_pin(self) -> None:
        self.assertEqual(pin_findings(VERIFY.read_text()), [])

    def test_no_action_installs_a_tool(self) -> None:
        actions = {each["uses"].split("@")[0] for job in self.data["jobs"].values() for each in job["steps"]
                   if "uses" in each}
        self.assertEqual(actions, {"actions/checkout", "actions/upload-artifact"})

    def test_each_job_installs_its_tools_right_after_the_checkout(self) -> None:
        self.assertEqual(set(self.data["jobs"]), set(VERIFY_TOOLS))
        for job_name, tools in VERIFY_TOOLS.items():
            steps = self.data["jobs"][job_name]["steps"]
            with self.subTest(job=job_name):
                self.assertTrue(steps[0]["uses"].startswith("actions/checkout@"))
                self.assertEqual(steps[1]["name"], INSTALL_TOOLS)
                self.assertEqual(steps[1]["shell"], "bash")
                self.assertNotIn("if", steps[1])
                self.assertEqual({TOOL_NAME.match(name).group(1) for name, _ in fetches(steps[1]["run"])}, tools)
                # Only a fetch or a tar names just. A word after just on another line would run a recipe.
                for line in steps[1]["run"].splitlines():
                    if not re.match(r"\s*(fetch|tar)\s", line):
                        self.assertNotRegex(line, r"\bjust\b[\"')]*(\s+\S|\s*$)")

    def test_each_download_goes_through_fetch_and_has_its_pins(self) -> None:
        others = [line for line in VERIFY.read_text().splitlines()
                  if re.search(r"\b(curl|wget)\b", line) and line.strip() != FETCH_CURL]
        self.assertEqual(others, [])
        for job, run in install_steps(self.data).items():
            pins, used = pinned(run), set()
            for name, url in fetches(run):
                for file, link in files_of(name, url):
                    with self.subTest(job=job, file=file):
                        self.assertIn(file, pins)
                        self.assertNotIn("$", link)
                        used.add(file)
            self.assertEqual(set(pins), used, job)

    def test_each_tool_has_one_version_and_each_download_one_sha256_in_this_repository(self) -> None:
        self.assertEqual(drift(own_steps()), [])

    def test_the_smalldocs_of_ci_is_the_smalldocs_of_the_justfile(self) -> None:
        names = [name for run in install_steps(self.data).values() for name, _ in fetches(run)]
        [version] = {TOOL_NAME.match(name).group(2) for name in names if name.startswith("smalldocs-")}
        self.assertIn(f'smalldocs := "uvx --quiet smalldocs@{version}"', (ROOT / "Justfile").read_text())

    def test_the_drift_check_finds_two_versions_and_two_sha256_values(self) -> None:
        run = install_run()
        jlog = next(name for name in pinned(run) if name.startswith("jlog-"))
        other = run.replace(pinned(run)[jlog], "0" * 64)
        self.assertTrue(any(jlog in finding for finding in drift({"a": run, "b": other})))
        newer = run.replace("just-1.59.0-", "just-1.60.0-")
        self.assertTrue(any(finding.startswith("just:") for finding in drift({"a": run, "b": newer})))

    def test_the_scan_is_the_scan_of_jnterfaces(self) -> None:
        folder = jnterfaces_folder("tests/test_workflow_pins.py")

        def scan(text: str) -> str:
            body = text.split("# --- The scan of the missing pins.", 1)[1].split("\n", 1)[1]
            return body.split("# --- The end of the scan. ---", 1)[0].replace('YAML(typ="safe").load(text)',
                                                                             "yaml.safe_load(text)")

        theirs = (Path(folder) / "tests/test_workflow_pins.py").read_text()
        self.assertEqual(scan(Path(__file__).read_text()), scan(theirs),
                         f"the scan of the jnterfaces clone at {folder} is not this scan; update one of them")

    def test_the_pins_are_the_pins_of_jnterfaces(self) -> None:
        # The CI of jnterfaces and the docs-publish workflow of its docs role pin the same tools. The clone is the one
        # that the checks use, in CI the commit of scripts/jnterfaces_commit.
        theirs = jnterfaces_steps()
        folder = jnterfaces_folder(JNTERFACES_WORKFLOWS[1])
        self.assertTrue(theirs, f"the jnterfaces clone at {folder} has no step that installs the pinned tools. Set "
                                "JNTERFACES_DIR to a clone of the commit of scripts/jnterfaces_commit, or update it.")
        self.assertEqual(drift(own_steps() | theirs), [], f"the pins of the jnterfaces clone at {folder}")

    def test_each_job_runs_on_the_image_of_jnterfaces(self) -> None:
        # The starters, this CI and the CI of jnterfaces run on one image, the image of the key of the Rust cache.
        folder = jnterfaces_folder(JNTERFACES_WORKFLOWS[1])
        data = [starter(name) for name in STARTERS] + [self.data]
        data += [yaml.safe_load((folder / name).read_text()) for name in JNTERFACES_WORKFLOWS]
        images = {job.get("runs-on") for each in data for job in each["jobs"].values()}
        self.assertEqual(images, {IMAGE}, f"the images of this repository and of the jnterfaces clone at {folder}")

    def test_each_download_is_what_the_step_installs(self) -> None:
        # A tar of a file that no fetch checked, a URL of another version, or an install of smalldocs from PyPI, would
        # install a file that no pin checks.
        for place, run in own_steps().items():
            names = [name for name, _ in fetches(run)]
            with self.subTest(place=place):
                tars = re.findall(r'^\s*tar -xzf "\$work/([^"]+)" -C "\$bin" ', run, re.M)
                self.assertEqual(len(tars), len(re.findall(r"^\s*tar\s", run, re.M)))
                self.assertEqual(sorted(tars), sorted(name for name in names if name.endswith(".tar.gz")
                                                      and not name.startswith("jlog-")))
                installs = [line.strip() for line in run.splitlines()
                            if re.search(r"\buv\s+tool\b|\bpip3?\b|\bpipx\b", line)]
                self.assertEqual(installs, [f'uv tool install --quiet "$work/{name}"' for name in names
                                            if name.endswith(".whl")])
                for name, url in fetches(run):
                    version = TOOL_NAME.match(name).group(2)
                    if not name.endswith("install.sh"):
                        self.assertIn(version, url, name)
                self.assertEqual(run.rstrip().splitlines()[-1], 'echo "$bin" >> "$GITHUB_PATH"')


FAKE_CURL = """#!/bin/sh
# A curl for the tests: curl -fsSL --retry 3 -o FILE URL copies the file of the fixtures with the name of the end of
# URL, and writes URL to FAKE_CURL_LOG.
while [ $# -gt 0 ]; do
  case $1 in
    -o) out=$2; shift 2 ;;
    --retry) shift 2 ;;
    -*) shift ;;
    *) url=$1; shift ;;
  esac
done
printf '%s\\n' "$url" >> "$FAKE_CURL_LOG"
cp "$FAKE_RELEASES/${url##*/}" "$out" 2>/dev/null || { echo "curl: (22) 404 $url" >&2; exit 22; }
"""

# The install.sh of jlog for the tests: it checks the archive of the local release against its .sha256, as the real
# one does, then writes a jlog that prints its version.
FAKE_JLOG_INSTALL = """#!/bin/sh
set -eu
printf '%s\\n' "$*" > "$FAKE_JLOG_ARGS"
dir=${JLOG_RELEASE_BASE#file://}/v0.5.0
for f in "$dir"/jlog-*.tar.gz; do
  [ "$(awk '{ print $1 }' "$f.sha256")" = "$(shasum -a 256 "$f" | awk '{ print $1 }')" ] || exit 9
done
printf '#!/bin/sh\\necho jlog 0.5.0\\n' > "$4/jlog"
chmod 755 "$4/jlog"
"""


class InstallShellTests(unittest.TestCase):
    """Run the step that installs the pinned tools, as GitHub runs it, with a fake curl and fake releases. The pins of
    the step are swapped for the hashes of the fake releases."""

    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="ci-install-test-")
        self.addCleanup(scratch.cleanup)
        self.base = Path(scratch.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.releases = self.base / "releases"
        self.releases.mkdir()
        self.tools = self.base / "tools"
        self.tools.mkdir()
        for name, text in (("curl", FAKE_CURL),):
            (self.tools / name).write_text(text)
            (self.tools / name).chmod(0o755)
        if not shutil.which("sha256sum"):
            (self.tools / "sha256sum").write_text('#!/bin/sh\nexec shasum -a 256 "$@"\n')
            (self.tools / "sha256sum").chmod(0o755)
        machine = os.uname().machine
        # The step runs only on Linux, so the tests on macOS give it a uname that says Linux.
        (self.tools / "uname").write_text(f'#!/bin/sh\n[ "$1" = -s ] && echo Linux || echo {machine}\n')
        (self.tools / "uname").chmod(0o755)
        self.target = "x86_64-unknown-linux-musl" if machine in ("x86_64", "amd64") else "aarch64-unknown-linux-musl"
        self.run_text = install_run()
        self.hashes: dict[str, str] = {}
        for name, url in fetches(self.run_text):
            file, link = name.replace("$target", self.target), url.replace("$target", self.target)
            self.make(file, link.rsplit("/", 1)[1])
        self.log = self.base / "curl.log"
        self.output = self.base / "github_path"

    def make(self, file: str, served: str) -> None:
        """Make the fake release SERVED for the download FILE, and record its hash."""
        import hashlib
        import tarfile
        path = self.releases / served
        if file.endswith("install.sh"):
            path.write_text(FAKE_JLOG_INSTALL)
        else:
            tool = re.match(r"^([a-z-]+?)-v?[0-9]", file).group(1)
            members = {"uv": [f"uv-{self.target}/uv", f"uv-{self.target}/uvx"]}.get(tool, [tool])
            with tarfile.open(path, "w:gz") as archive:
                for member in members:
                    data = f"#!/bin/sh\necho {member}\n".encode()
                    info = tarfile.TarInfo(member)
                    info.size, info.mode = len(data), 0o755
                    import io
                    archive.addfile(info, io.BytesIO(data))
        self.hashes[file] = hashlib.sha256(path.read_bytes()).hexdigest()

    def script(self, hashes: dict[str, str] | None = None) -> str:
        block = "\n".join(f"{digest}  {name}" for name, digest in (hashes or self.hashes).items())
        head, rest = self.run_text.split("pins='", 1)
        return head + "pins='\n" + block + "\n'" + rest.split("'", 1)[1]

    def bash(self, script: str | None = None, **env: str) -> subprocess.CompletedProcess[str]:
        self.output.write_text("")
        full = {key: value for key, value in os.environ.items() if not key.startswith(("JN_", "JNPROFILE_"))}
        full.update(PATH=f"{self.tools}{os.pathsep}{os.environ['PATH']}", HOME=str(self.home),
                    GITHUB_PATH=str(self.output), FAKE_RELEASES=str(self.releases), FAKE_CURL_LOG=str(self.log),
                    FAKE_JLOG_ARGS=str(self.base / "jlog.args"), **env)
        return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script or self.script()],
                              capture_output=True, text=True, env=full, cwd=self.base)

    def installed(self) -> set[str]:
        folder = self.home / ".local/bin"
        return {item.name for item in folder.iterdir()} if folder.is_dir() else set()

    def downloads(self) -> list[str]:
        return [line.rsplit("/", 1)[1] for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_the_tools_install_and_their_folder_goes_on_the_path(self) -> None:
        done = self.bash()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.installed(), {"just", "uv", "uvx", "jlog"})
        self.assertEqual(self.output.read_text(), f"{self.home}/.local/bin\n")
        self.assertNotIn("cargo-llvm-cov", " ".join(self.downloads()))
        # install.sh of jlog takes the pinned archive from the local release, never from the server.
        args = (self.base / "jlog.args").read_text().split()
        self.assertEqual(args[:2], ["--tag", "v0.5.0"])
        self.assertEqual(sum("/rahuldave/jlog/" in line for line in self.log.read_text().splitlines()), 2)

    def test_the_tools_of_rust_install_only_when_asked(self) -> None:
        done = self.bash(JN_RUST_TOOLS="1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.installed(), {"just", "uv", "uvx", "jlog", "cargo-llvm-cov"})
        done = self.bash(JN_RUST_TOOLS="1", JNPROFILE_RUST_NEXTEST="1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("cargo-nextest", self.installed())
        shutil.rmtree(self.home / ".local")
        done = self.bash(JNPROFILE_RUST_NEXTEST="1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.installed(), {"just", "uv", "uvx", "jlog"})

    def test_a_download_that_does_not_match_its_pin_stops_the_step(self) -> None:
        for name in self.hashes:
            wrong = dict(self.hashes, **{name: "0" * 64})
            shutil.rmtree(self.home / ".local", ignore_errors=True)
            done = self.bash(self.script(wrong), JN_RUST_TOOLS="1", JNPROFILE_RUST_NEXTEST="1")
            with self.subTest(download=name):
                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertIn(f"::error::The SHA-256 of {name} is ", done.stdout)
                tool = re.match(r"^([a-z-]+?)-v?[0-9]", name).group(1)
                self.assertNotIn(tool, self.installed())
                self.assertEqual(self.output.read_text(), "")

    def test_a_download_with_no_pin_stops_before_the_download(self) -> None:
        name = f"just-1.59.0-{self.target}.tar.gz"
        done = self.bash(self.script({key: value for key, value in self.hashes.items() if key != name}))
        self.assertEqual(done.returncode, 1)
        self.assertIn(f"::error::No pinned SHA-256 for {name}.", done.stdout)
        self.assertEqual(self.downloads(), [])

    def test_a_machine_that_is_not_linux_stops_the_step(self) -> None:
        (self.tools / "uname").write_text('#!/bin/sh\n[ "$1" = -s ] && echo Darwin || echo arm64\n')
        (self.tools / "uname").chmod(0o755)
        done = self.bash()
        self.assertEqual(done.returncode, 1)
        self.assertIn("::error::The pinned tools are for Linux, not Darwin.", done.stdout)
        self.assertEqual(self.downloads(), [])

    def test_a_failed_download_stops_the_step(self) -> None:
        (self.releases / f"uv-{self.target}.tar.gz").unlink()
        done = self.bash()
        self.assertNotEqual(done.returncode, 0)
        self.assertNotIn("jlog", self.installed())
        self.assertEqual(self.output.read_text(), "")


OLD_TIME = 946684800
GUARD = "Check that the check left the path dependencies as they were"
APP_MAIN = 'fn main() { println!("{} {}", m::M, a::value()); }\n'


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def package(name: str, deps: str = "") -> str:
    return f'[package]\nname = "{name}"\nversion = "0.1.0"\nedition = "2021"\n' + (f"\n[dependencies]\n{deps}" if deps else "")


@unittest.skipUnless(sys.version_info >= (3, 11) and shutil.which("cargo"), "needs cargo and Python 3.11 or later")
class PathDependencyTests(unittest.TestCase):
    """Run the step that sets the times of the path dependencies, as GitHub runs it, in a scratch workspace: a root
    package, the member crates/m, the path dependency vendor/a, its own path dependency vendor/b, the patch
    vendor/ffi, and a path dependency outside the repository. Then build with cargo to show what the times do."""

    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="ci-path-deps-")
        self.addCleanup(scratch.cleanup)
        self.base = Path(scratch.name).resolve()
        self.origin = self.base / "origin"
        outside = self.base / "outside"
        write(outside / "Cargo.toml", package("outside"))
        write(outside / "src/lib.rs", "")
        write(self.origin / "Cargo.toml", package("app", 'm = { path = "crates/m" }\na = { path = "vendor/a" }\n'
                                                   f'outside = {{ path = "{outside}" }}\n')
              + '\n[workspace]\nmembers = ["crates/m"]\nexclude = ["vendor"]\n\n'
                '[patch.crates-io]\nffi = { path = "vendor/ffi" }\n')
        write(self.origin / "src/main.rs", APP_MAIN)
        write(self.origin / "crates/m/Cargo.toml", package("m"))
        write(self.origin / "crates/m/src/lib.rs", 'pub const M: &str = "m";\n')
        write(self.origin / "vendor/a/Cargo.toml", package("a", 'b = { path = "../b" }\n'))
        write(self.origin / "vendor/a/src/lib.rs", "pub fn value() -> &'static str { b::B }\n")
        write(self.origin / "vendor/b/Cargo.toml", package("b"))
        write(self.origin / "vendor/b/src/lib.rs", 'pub const B: &str = "one";\n')
        write(self.origin / "vendor/ffi/Cargo.toml", package("ffi"))
        write(self.origin / "vendor/ffi/src/lib.rs", "")
        write(self.origin / ".gitignore", "/target/\n")
        self.git("init", "-qb", "main", cwd=self.origin)
        self.git("add", ".", cwd=self.origin)
        self.git("commit", "-qm", "one", cwd=self.origin)
        self.tools = self.base / "tools"
        self.tools.mkdir()
        (self.tools / "python3").symlink_to(sys.executable)
        self.run_text = step(starter("github-check.yml")["jobs"]["ci"], PATH_DEPS)["run"]
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("JN_", "CARGO_TARGET_DIR", "CARGO_BUILD", "RUSTFLAGS", "CARGO_INCREMENTAL"))}
        self.env["PATH"] = f"{self.tools}{os.pathsep}{os.environ['PATH']}"

    def git(self, *args: str, cwd: Path) -> str:
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                              check=True, capture_output=True, text=True).stdout

    def clone(self, name: str, ref: str = "main") -> Path:
        folder = self.base / name
        self.git("clone", "-q", str(self.origin), str(folder), cwd=self.base)
        self.git("checkout", "-q", ref, cwd=folder)
        return folder

    def step(self, folder: Path, on: bool = True, run: str | None = None, **env: str) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
        output = self.base / f"output-{folder.name}"
        output.write_text("")
        full = dict(self.env, GITHUB_OUTPUT=str(output), **env)
        if on:
            full["JN_CI_PATH_DEP_TIMES"] = "1"
        done = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", run or self.run_text],
                              cwd=folder, capture_output=True, text=True, env=full)
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        return done, values

    def cargo(self, folder: Path) -> str:
        done = subprocess.run(["cargo", "build", "--offline", "-v"], cwd=folder, capture_output=True, text=True,
                              env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stderr

    def program(self, folder: Path) -> str:
        return subprocess.run([str(folder / "target/debug/app")], capture_output=True, text=True, check=True).stdout

    def test_both_check_jobs_run_the_same_step_before_the_restore(self) -> None:
        for name, job_name in CHECK_JOBS.items():
            found = step(starter(name)["jobs"][job_name], PATH_DEPS)
            with self.subTest(starter=name):
                self.assertEqual(found["run"], self.run_text)
                self.assertEqual(found["id"], "path-deps")
                self.assertEqual(found["if"], RUST)
                self.assertEqual(found["shell"], "bash")
                # The step is off unless the project turns it on, so no starter sets the variable.
                self.assertNotIn("JN_CI_PATH_DEP_TIMES", str(starter(name).get("env")) + str(
                    starter(name)["jobs"][job_name].get("env")) + str(found.get("env")))

    def test_without_the_variable_the_hash_is_none_and_no_time_changes(self) -> None:
        folder = self.clone("off")
        before = (folder / "vendor/b/src/lib.rs").stat().st_mtime
        for value in ("", "0", "true", "yes"):
            done, values = self.step(folder, on=False, JN_CI_PATH_DEP_TIMES=value)
            with self.subTest(value=value):
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(values, {"hash": "none"})
        self.assertEqual((folder / "vendor/b/src/lib.rs").stat().st_mtime, before)

    def test_the_step_finds_the_path_dependencies_and_gives_only_them_the_old_time(self) -> None:
        folder = self.clone("on")
        member = (folder / "crates/m/src/lib.rs").stat().st_mtime
        done, values = self.step(folder)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertRegex(values["hash"], r"^[0-9a-f]{64}$")
        # A path dependency of a member, one of a path dependency, and one of the patch; not the member, not the
        # root package, and not the package outside the repository.
        self.assertEqual(json.loads(values["folders"]), ["vendor/a", "vendor/b", "vendor/ffi"])
        for name in ("vendor/a/src/lib.rs", "vendor/a/Cargo.toml", "vendor/b/src/lib.rs", "vendor/ffi/src/lib.rs",
                     "vendor/a/src", "vendor/a"):
            with self.subTest(path=name):
                self.assertEqual((folder / name).stat().st_mtime, OLD_TIME)
        self.assertEqual((folder / "crates/m/src/lib.rs").stat().st_mtime, member)
        self.assertNotEqual((folder / "src/main.rs").stat().st_mtime, OLD_TIME)
        self.assertNotEqual((folder / "vendor").stat().st_mtime, OLD_TIME)
        self.assertNotEqual((self.base / "outside/src/lib.rs").stat().st_mtime, OLD_TIME)

    def test_the_hash_follows_the_files_of_the_path_dependencies_only(self) -> None:
        first = self.step(self.clone("first"))[1]["hash"]
        self.assertEqual(self.step(self.clone("again"))[1]["hash"], first)
        # A change of a member or of the root package keeps the hash, so the cache stays warm.
        write(self.origin / "crates/m/src/lib.rs", 'pub const M: &str = "m2";\n')
        self.git("commit", "-qam", "member", cwd=self.origin)
        self.assertEqual(self.step(self.clone("member"))[1]["hash"], first)
        # A change of a file of a path dependency, of its mode, or a new file there changes it.
        changes = [("content", lambda: write(self.origin / "vendor/b/src/lib.rs", 'pub const B: &str = "two";\n')),
                   ("new file", lambda: write(self.origin / "vendor/ffi/build.rs", "fn main() {}\n")),
                   ("mode", lambda: (self.origin / "vendor/ffi/build.rs").chmod(0o755))]
        seen = {first}
        for label, change in changes:
            change()
            self.git("add", "-A", cwd=self.origin)
            self.git("commit", "-qm", label, cwd=self.origin)
            digest = self.step(self.clone(label.replace(" ", "-")))[1]["hash"]
            with self.subTest(change=label):
                self.assertNotIn(digest, seen)
            seen.add(digest)

    def test_a_changed_path_dependency_stops_the_step_before_any_time_changes(self) -> None:
        folder = self.clone("dirty")
        write(folder / "vendor/b/src/lib.rs", 'pub const B: &str = "local";\n')
        before = (folder / "vendor/a/src/lib.rs").stat().st_mtime
        done, values = self.step(folder)
        self.assertEqual(done.returncode, 1)
        self.assertIn("::error::A path dependency has changes after the checkout", done.stdout)
        self.assertEqual(values, {})
        self.assertEqual((folder / "vendor/a/src/lib.rs").stat().st_mtime, before)

    def test_a_link_in_a_path_dependency_keeps_the_time_of_its_target(self) -> None:
        # A link to a file outside the path dependencies: its target is not in the hash, so it keeps its time.
        (self.origin / "vendor/a/src/shared.rs").symlink_to("../../../crates/m/src/lib.rs")
        self.git("add", "-A", cwd=self.origin)
        self.git("commit", "-qm", "link", cwd=self.origin)
        folder = self.clone("link")
        member = (folder / "crates/m/src/lib.rs").stat().st_mtime
        done, _ = self.step(folder)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((folder / "crates/m/src/lib.rs").stat().st_mtime, member)

    def test_a_link_that_names_another_file_changes_the_hash(self) -> None:
        # cargo follows a link, so a link that names another file of the path dependency is a change of its input.
        for name in ("a.txt", "b.txt"):
            write(self.origin / f"vendor/ffi/src/{name}", name + "\n")
        (self.origin / "vendor/ffi/src/data.txt").symlink_to("a.txt")
        self.git("add", "-A", cwd=self.origin)
        self.git("commit", "-qm", "a", cwd=self.origin)
        first = self.step(self.clone("link-a"))[1]["hash"]
        (self.origin / "vendor/ffi/src/data.txt").unlink()
        (self.origin / "vendor/ffi/src/data.txt").symlink_to("b.txt")
        self.git("add", "-A", cwd=self.origin)
        self.git("commit", "-qm", "b", cwd=self.origin)
        self.assertNotEqual(self.step(self.clone("link-b"))[1]["hash"], first)

    def test_a_gitattributes_that_changes_the_bytes_changes_the_hash(self) -> None:
        # The blobs stay, but the checkout writes other bytes, so the hash reads the bytes on the disk.
        first = self.step(self.clone("plain-eol"))[1]["hash"]
        write(self.origin / ".gitattributes", "vendor/** text eol=crlf\n")
        self.git("add", "-A", cwd=self.origin)
        self.git("commit", "-qm", "crlf", cwd=self.origin)
        folder = self.clone("crlf")
        self.assertIn(b"\r\n", (folder / "vendor/b/src/lib.rs").read_bytes())
        self.assertNotEqual(self.step(folder)[1]["hash"], first)

    def test_a_submodule_in_a_path_dependency_is_in_the_hash_and_keeps_its_time(self) -> None:
        sub = self.base / "sub"
        write(sub / "x.c", "int x;\n")
        self.git("init", "-qb", "main", cwd=sub)
        self.git("add", ".", cwd=sub)
        self.git("commit", "-qm", "x", cwd=sub)
        first = self.step(self.clone("no-sub"))[1]["hash"]
        self.git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "vendor/ffi/sub",
                 cwd=self.origin)
        self.git("commit", "-qm", "sub", cwd=self.origin)
        folder = self.clone("with-sub")
        self.git("-c", "protocol.file.allow=always", "submodule", "update", "-q", "--init", cwd=folder)
        done, values = self.step(folder)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotEqual(values["hash"], first)
        self.assertNotEqual((folder / "vendor/ffi/sub/x.c").stat().st_mtime, OLD_TIME)

    def test_a_crate_in_vendor_that_is_a_member_gets_a_warning(self) -> None:
        # cargo makes a path dependency under the root a member unless workspace.exclude names it.
        text = (self.origin / "Cargo.toml").read_text().replace('exclude = ["vendor"]', "exclude = []")
        text = text.replace(f'outside = {{ path = "{self.base / "outside"}" }}\n', "")
        write(self.origin / "Cargo.toml", text.replace('[patch.crates-io]\nffi = { path = "vendor/ffi" }\n', ""))
        self.git("commit", "-qam", "members", cwd=self.origin)
        done, values = self.step(self.clone("members"))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(values, {"hash": "none"})
        self.assertIn("::warning::JN_CI_PATH_DEP_TIMES is 1, but the step found no path dependency", done.stdout)
        self.assertIn("workspace.exclude", done.stdout)

    def test_no_path_dependency_gives_none(self) -> None:
        folder = self.base / "plain"
        write(folder / "Cargo.toml", package("plain"))
        write(folder / "src/main.rs", "fn main() {}\n")
        self.git("init", "-qb", "main", cwd=folder)
        self.git("add", ".", cwd=folder)
        self.git("commit", "-qm", "plain", cwd=folder)
        done, values = self.step(folder)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(values, {"hash": "none"})

    def test_cargo_reuses_a_build_of_the_same_files_and_builds_the_project_again(self) -> None:
        built = self.clone("built")
        self.step(built)
        self.cargo(built)
        # A later fresh checkout of the same commit, with the build restored as the cache would restore it.
        time.sleep(1.1)
        fresh = self.clone("fresh")
        subprocess.run(["cp", "-p", "-R", str(built / "target"), str(fresh / "target")], check=True)
        done, values = self.step(fresh)
        self.assertEqual(done.returncode, 0, done.stderr)
        log = self.cargo(fresh)
        for crate in ("a", "b"):
            self.assertRegex(log, rf"Fresh {crate} v0\.1\.0")
        # The root package and the member have the time of the checkout, so cargo builds them again.
        self.assertRegex(log, r"Compiling app v0\.1\.0")
        self.assertRegex(log, r"Compiling m v0\.1\.0")
        self.assertEqual(self.program(fresh), "m one\n")

    def test_the_hash_keeps_a_build_of_other_files_out(self) -> None:
        # The danger that the hash in each level of the key guards against: with old times, cargo takes a build of
        # other files of a path dependency as up to date, and the program runs the old code, a false pass.
        built = self.clone("old")
        old = self.step(built)[1]["hash"]
        self.cargo(built)
        write(self.origin / "vendor/b/src/lib.rs", 'pub const B: &str = "two";\n')
        self.git("commit", "-qam", "two", cwd=self.origin)
        time.sleep(1.1)
        fresh = self.clone("new")
        subprocess.run(["cp", "-p", "-R", str(built / "target"), str(fresh / "target")], check=True)
        new = self.step(fresh)[1]["hash"]
        self.assertNotEqual(new, old)
        self.assertRegex(self.cargo(fresh), r"Fresh b v0\.1\.0")
        self.assertEqual(self.program(fresh), "m one\n")
        # So no level of the key may restore across a change of the hash.
        restore = step(starter("github-release.yml")["jobs"]["check"], "Restore the Rust cache")
        for level in [restore["with"]["key"]] + restore["with"]["restore-keys"].strip().splitlines():
            self.assertIn("-paths-${{ steps.path-deps.outputs.hash }}-", level)

    def test_the_guard_finds_a_check_that_changed_a_path_dependency(self) -> None:
        guard = step(starter("github-release.yml")["jobs"]["check"], GUARD)
        self.assertEqual(guard["env"], {"FOLDERS": "${{ steps.path-deps.outputs.folders }}"})
        self.assertEqual(guard["if"], "steps.path-deps.outputs.hash != '' && steps.path-deps.outputs.hash != 'none'")
        names = [each.get("name") for each in starter("github-release.yml")["jobs"]["check"]["steps"]]
        self.assertEqual(names.index(GUARD), names.index("Check") + 1)
        self.assertEqual(names.index("Save the Rust cache"), names.index(GUARD) + 1)
        folder = self.clone("guard")
        _, values = self.step(folder)
        cases = {"clean": (None, {}), "changed": ("vendor/b/src/lib.rs", {"changed": "true"}),
                 "new file": ("vendor/a/src/new.rs", {"changed": "true"}), "member": ("crates/m/src/x.rs", {})}
        for label, (path, want) in cases.items():
            if path:
                write(folder / path, "// made by the check\n")
            _, after = self.step(folder, on=False, run=guard["run"], FOLDERS=values["folders"])
            with self.subTest(case=label):
                self.assertEqual(after, want)
            if path:
                self.git("checkout", "-q", "--", ".", cwd=folder)
                self.git("clean", "-qfd", cwd=folder)
        # A list of no folder never passes.
        _, after = self.step(folder, on=False, run=guard["run"], FOLDERS="[]")
        self.assertEqual(after, {"changed": "true"})


if __name__ == "__main__":
    unittest.main()
