"""Check the Rust steps of the CI starters of gsu: github-check.yml and github-release.yml.

The Rust steps run only in a project with a toolchain file, rust-toolchain.toml or rust-toolchain. They read the
toolchain from the file and name no channel, restore a cache of the build, and save it only on a push to main. The key
of the cache holds the compiler that rustc -V prints, the word check that each job of just check shares, the hash of
each Cargo.lock and the commit. A project with a Cargo.toml and no toolchain file fails with a message that names the
fix. A project in another language skips each Rust step. The tests parse the YAML with PyYAML, and run the shell of
the toolchain steps with bash, a fake rustup and rustc, and Python 3.11 or later, for tomllib.
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
STOP = "Stop a Rust project that has no toolchain file"
# The condition of the install, as in the docs-publish workflow of jnterfaces.
HAS_TOOLCHAIN = "hashFiles('rust-toolchain.toml', 'rust-toolchain') != ''"
NO_TOOLCHAIN = "hashFiles('Cargo.toml') != '' && hashFiles('rust-toolchain.toml', 'rust-toolchain') == ''"
PATHS = ["~/.cargo/registry/index", "~/.cargo/registry/cache", "~/.cargo/git/db", "target/"]
# The word check stands for the build of just check, so the jobs of a pull request and of main share the cache.
PREFIX = "${{ runner.os }}-${{ runner.arch }}-rust-${{ steps.rust.outputs.toolchain }}-check-"
LOCK = PREFIX + "${{ hashFiles('**/Cargo.lock') }}-"
KEY = LOCK + "${{ github.sha }}"
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

    def test_each_check_job_restores_with_the_shared_key(self) -> None:
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
                # The newest cache with the same Cargo.lock first, then the newest of the same compiler.
                self.assertEqual(restore["with"]["restore-keys"].strip().splitlines(), [LOCK, PREFIX])

    def test_the_key_has_its_parts_in_order(self) -> None:
        key = step(starter("github-check.yml")["jobs"]["ci"], "Restore the Rust cache")["with"]["key"]
        parts = re.findall(r"\$\{\{ ([^}]+) \}\}|-(check)-", key)
        self.assertEqual([expr or word for expr, word in parts],
                         ["runner.os", "runner.arch", "steps.rust.outputs.toolchain", "check",
                          "hashFiles('**/Cargo.lock')", "github.sha"])

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

    def test_cargo_nextest_is_a_pinned_release_binary_only_with_the_variable(self) -> None:
        for name, job_name in CHECK_JOBS.items():
            with self.subTest(starter=name):
                job = starter(name)["jobs"][job_name]
                names = [each.get("name") for each in job["steps"]]
                found = step(job, "Install cargo-nextest")
                self.assertEqual(found["uses"], "taiki-e/install-action@v2")
                self.assertRegex(found["with"]["tool"], r"^cargo-nextest@[0-9]+\.[0-9]+\.[0-9]+$")
                self.assertEqual(found["if"], f"{RUST} && env.JNPROFILE_RUST_NEXTEST == '1'")
                # After cargo-llvm-cov, and before the restore and the checks.
                self.assertEqual(names.index("Install cargo-nextest"), names.index("Install cargo-llvm-cov") + 1)
                self.assertNotIn("JNPROFILE_RUST_NEXTEST", str(job.get("env")) + str(starter(name).get("env")))
        self.assertNotIn("Install cargo-nextest",
                         [each.get("name") for each in starter("github-release.yml")["jobs"]["release"]["steps"]])

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


if __name__ == "__main__":
    unittest.main()
