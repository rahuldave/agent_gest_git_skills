"""CI runs just check and no other check, so a developer finds each failure of CI with just check.

The job verify of verify.yml runs just check and no other recipe, with the whole history for release-check. The job
release stays as it was: it runs just release after verify, on a push to main. The tests need just, and PyYAML.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/verify.yml"
# The recipes that just check must run: each check that CI ran before just check, and the checks of the other repos.
STEPS = ["release-check", "ci-gate", "lint", "package-lint", "stack-rebase-lab", "install-test", "source-archive", "docs-check", "diff-check"]
# The steps of the job verify that set up a clone or a program, and the step that runs just check.
PINNED_TOOLS = "Install the pinned tools"
SETUP = {"Get jnterfaces, whose link checker the lint runs and whose installer install-test runs", PINNED_TOOLS}
CHECK = "Check the release, the gate trailers, the lint, the manifest, the labs, the install, the source archive, the docs site and the diff"
# The actions of the job verify. A check in an action would be a check that just check does not run.
CHECKOUT = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
VERIFY_ACTIONS = [CHECKOUT, "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"]
# The steps of the job release, as they were before just check came: CI tags each release after verify passed.
RELEASE_STEPS = [
    {"uses": CHECKOUT, "with": {"fetch-depth": 0}},
    {"name": PINNED_TOOLS, "shell": "bash"},
    {"name": "Name the author of the tag",
     "run": 'git config user.name "github-actions[bot]"\n'
            'git config user.email "41898282+github-actions[bot]@users.noreply.github.com"\n'},
    {"name": "Tag the release", "id": "release", "run": "just release"},
]
# The tag of jlog that the CI of jnterfaces pins.
JLOG = "v0.5.0"
# The lines that make github-actions[bot] the author of the commit of gh-pages, as in the job release.
DOCS_AUTHOR = ['git config user.name "github-actions[bot]"',
               'git config user.email "41898282+github-actions[bot]@users.noreply.github.com"']


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
        # The step that installs the pinned tools checks each download with sha256sum and installs just itself.
        for name in SETUP - {PINNED_TOOLS}:
            # A URL names a file of another repository, such as the install.sh of jlog, not a script of this one.
            local = re.sub(r"https://\S+", "", runs[name])
            self.assertNotRegex(local, r"\bjust\b|scripts/\S+\.(sh|py)|git archive|sha256sum|shasum", name)

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
        # CI fetches the archive of the release and the install.sh of the commit of the tag, each against a pin.
        want = [f'fetch "jlog-{JLOG}-$target.tar.gz" '
                f'"https://github.com/rahuldave/jlog/releases/download/{JLOG}/jlog-$target.tar.gz"',
                f"fetch jlog-{JLOG}-install.sh https://raw.githubusercontent.com/rahuldave/jlog/{JLOG_FULL_COMMIT}"
                "/scripts/install.sh"]
        self.assertEqual([line for line in runs(self.jobs["verify"]) if "rahuldave/jlog" in line], want)
        [step] = [step for step in self.jobs["verify"]["steps"] if "rahuldave/jlog" in (step.get("run") or "")]
        self.assertEqual(step.get("shell"), "bash")
        self.assertIn('echo "$bin" >> "$GITHUB_PATH"', step["run"])
        # uv comes first, so install.sh makes the environments of the plugins of jlog.
        self.assertLess(step["run"].index('tar -xzf "$work/uv-0.13.7-$target.tar.gz"'),
                        step["run"].index(f'sh "$work/jlog-{JLOG}-install.sh"'))
        self.assertNotRegex(WORKFLOW.read_text(), r"\|\s*sh\b")

    def test_each_starter_installs_jlog_as_ci_does(self) -> None:
        # Each job of the starters installs the tag of jlog that CI pins, with the step that checks each download
        # against a pin in the file: the archive of the release and the install.sh of the commit of the tag.
        want = ['fetch "jlog-v0.5.0-$target.tar.gz" '
                '"https://github.com/rahuldave/jlog/releases/download/v0.5.0/jlog-$target.tar.gz"',
                f"fetch jlog-v0.5.0-install.sh https://raw.githubusercontent.com/rahuldave/jlog/{JLOG_FULL_COMMIT}"
                "/scripts/install.sh"]
        for name in ("github-check.yml", "github-release.yml"):
            text = (ROOT / ".agents/skills/gsu/assets/templates" / name).read_text()
            jobs = yaml.safe_load(text)["jobs"]
            for job_name, job in jobs.items():
                with self.subTest(starter=name, job=job_name):
                    self.assertEqual([line for line in runs(job) if "rahuldave/jlog" in line], want)
                    [step] = [step for step in job["steps"] if "rahuldave/jlog" in (step.get("run") or "")]
                    self.assertEqual(step.get("shell"), "bash")
                    self.assertIn('echo "$bin" >> "$GITHUB_PATH"', step["run"])
                    # uv comes first in the same step, so install.sh finds it and makes the environments of the
                    # plugins of jlog.
                    self.assertLess(step["run"].index('tar -xzf "$work/uv-0.13.7-$target.tar.gz"'),
                                    step["run"].index('sh "$work/jlog-v0.5.0-install.sh"'))
            # jlog comes from install.sh, so no cargo builds it, and no script goes from curl into a shell.
            self.assertNotRegex(text, r"cargo b?install")
            self.assertNotRegex(text, r"\|\s*sh\b")

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
        # The run of the install step is the same as in the job verify, which the test above checks.
        self.assertEqual([{k: v for k, v in step.items() if not (step.get("name") == PINNED_TOOLS and k == "run")}
                          for step in job["steps"]], RELEASE_STEPS)
        # A later job checks out the tag that the release gives, which can be on the version commit.
        self.assertEqual(job["outputs"], {"tag": "${{ steps.release.outputs.tag }}"})

    def test_only_the_jobs_release_and_docs_can_write(self) -> None:
        self.assertEqual(yaml.safe_load(WORKFLOW.read_text())["permissions"], {"contents": "read"})
        for name, job in self.jobs.items():
            if name not in ("release", "docs"):
                self.assertNotIn("permissions", job, name)
        self.assertEqual(self.jobs["docs"]["permissions"], {"contents": "write"})

    def test_docs_runs_after_verify_on_a_push_to_main(self) -> None:
        job = self.jobs["docs"]
        self.assertEqual(job["needs"], "verify")
        self.assertEqual(job["if"], "github.event_name == 'push' && github.ref == 'refs/heads/main'")
        # One publish at a time, and a newer run cancels an older one.
        self.assertEqual(job["concurrency"], {"group": "docs", "cancel-in-progress": True})

    def test_docs_commits_to_gh_pages_as_the_bot(self) -> None:
        lines = runs(self.jobs["docs"])
        for line in DOCS_AUTHOR:
            self.assertIn(line, lines)
        names = [step.get("name") for step in self.jobs["docs"]["steps"]]
        self.assertLess(names.index("Name the author of the commit of gh-pages"), len(names) - 1)

    def test_docs_publishes_the_tip_of_main_and_not_its_own_commit(self) -> None:
        # A run that publishes its own commit, after the run of a newer push, would put an older site on gh-pages.
        last = self.jobs["docs"]["steps"][-1]
        self.assertEqual(last.get("shell"), "bash", "bash in Actions stops at the first failed line")
        lines = [line.strip() for line in last["run"].splitlines() if line.strip()]
        self.assertEqual(lines[:2], ["git fetch --quiet origin main", "git checkout --quiet --detach FETCH_HEAD"])
        self.assertEqual(lines[-1], "just docs-publish")
        for step in self.jobs["docs"]["steps"][:-1]:
            self.assertNotIn("docs-publish", step.get("run") or "", step.get("name"))

    def test_docs_publish_builds_the_site_in_strict_mode_first(self) -> None:
        dump = subprocess.run(["just", "--justfile", str(ROOT / "Justfile"), "--dump", "--dump-format", "json"],
                              check=True, capture_output=True, text=True).stdout
        recipes = json.loads(dump)["recipes"]
        self.assertIn("docs-build", [dependency["recipe"] for dependency in recipes["docs-publish"]["dependencies"]])
        body = " ".join(part for line in recipes["docs-build"]["body"] for part in line if isinstance(part, str))
        self.assertIn("--strict", body)

    def test_no_failure_of_docs_is_hidden(self) -> None:
        self.assertNotIn("continue-on-error", self.jobs["docs"])
        for step in self.jobs["docs"]["steps"]:
            self.assertNotIn("continue-on-error", step, step.get("name") or step.get("uses"))


# A line that names jlog names only the version of jlog, so each version on such a line is a pin: in an install, the
# key of a cache, the name of a step, a variable or a comment. A version may lack the v. Each must be JLOG.
JLOG_LINE = re.compile(r"jlog", re.IGNORECASE)
VERSION = re.compile(r"(?<![\w.])v?([0-9]+\.[0-9]+\.[0-9]+)(?![\w.])")
INSTALL = re.compile(r"cargo (b?install)\b.*\bjlog\b")
PINNED_INSTALL = re.compile(r"--tag v[0-9]+\.[0-9]+\.[0-9]+ jlog$")
# The install.sh of jlog: it comes from a tag, not from a branch, and installs the release of that tag.
INSTALLER = re.compile(r"rahuldave/jlog/\S*install\.sh")
# A download of a release of jlog, by a URL or by gh. It must name its version.
DOWNLOAD = re.compile(r"rahuldave/jlog/\S*releases|gh release download\b.*\bjlog\b")
PINNED_INSTALLER = re.compile(r"rahuldave/jlog/(v[0-9]+\.[0-9]+\.[0-9]+)/scripts/install\.sh \| sh -s -- --tag \1$")
# The CI starters fetch install.sh from the full SHA of the commit of the tag, and check it against a pin.
COMMIT_INSTALLER = re.compile(r"rahuldave/jlog/([0-9a-f]{40})/scripts/install\.sh$")
# The commit of the tag of jlog, which the comment next to each install names.
JLOG_COMMIT = "224a622"
JLOG_FULL_COMMIT = "224a622a27920256e3d6ad6a8363c9ea96078a20"
TAG_COMMIT = re.compile(r"\bis the commit ([0-9a-f]{7,40})\b")


def jlog_pins(files: dict[str, str]) -> tuple[list[tuple[str, str]], list[str]]:
    """The pins of jlog in the text of each file, as pairs of a place and a version with a v, and the findings: a
    cargo install of jlog with no pin at its end, an install.sh of jlog that does not come from the tag that it
    installs, or a comment that names another commit for the tag of jlog."""
    pins, findings = [], []
    for name, text in files.items():
        for number, line in enumerate(text.splitlines(), 1):
            if not JLOG_LINE.search(line):
                continue
            place = f"{name}:{number}"
            pins += [(place, f"v{version}") for version in VERSION.findall(line)]
            if INSTALL.search(line) and not PINNED_INSTALL.search(line.strip()):
                findings.append(f"{place}: a cargo install of jlog without --tag VERSION jlog at the end")
            commit_pin = COMMIT_INSTALLER.search(line.strip())
            if commit_pin and commit_pin.group(1) != JLOG_FULL_COMMIT:
                findings.append(f"{place}: the install.sh of jlog comes from {commit_pin.group(1)}, not the tag")
            elif INSTALLER.search(line) and not commit_pin and not PINNED_INSTALLER.search(line.strip()):
                findings.append(f"{place}: an install.sh of jlog that is not from the tag of --tag VERSION at the end")
            if DOWNLOAD.search(line) and not VERSION.search(line):
                findings.append(f"{place}: a download of jlog that names no version")
            commit = TAG_COMMIT.search(line)
            if commit and not JLOG_COMMIT.startswith(commit.group(1)[:7]):
                findings.append(f"{place}: the tag of jlog is the commit {JLOG_COMMIT}, not {commit.group(1)}")
    return pins, findings


def repository_files() -> dict[str, str]:
    """The text of each file that git tracks, and of each new file that git does not ignore. A file that is not text
    is skipped, and so is this test file, whose probe lines name wrong pins on purpose."""
    names = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                           check=True, capture_output=True, text=True).stdout.split("\0")
    files = {}
    for name in filter(None, names):
        path = ROOT / name
        if not path.is_file() or path == Path(__file__).resolve():
            continue
        try:
            files[name] = path.read_text()
        except UnicodeDecodeError:
            continue
    return files


class JlogPinTests(unittest.TestCase):
    """Each pin of jlog in the repository, in CI and in the CI starters, is the same version, so no pin drifts."""

    def test_each_pin_of_jlog_is_the_same(self) -> None:
        pins, findings = jlog_pins(repository_files())
        self.assertEqual(findings, [])
        places = {place.split(":")[0] for place, _ in pins}
        self.assertLessEqual({".github/workflows/verify.yml", ".agents/skills/gsu/assets/templates/github-check.yml",
                              ".agents/skills/gsu/assets/templates/github-release.yml"}, places)
        self.assertEqual({version for _, version in pins}, {JLOG}, [pin for pin in pins if pin[1] != JLOG])

    def test_the_scan_finds_each_form_of_a_pin(self) -> None:
        for line in ("key: jlog-v0.1.1-${{ runner.os }}", "key: jlog-0.1.1-${{ runner.os }}",
                     "run: cargo install --locked --git https://github.com/rahuldave/jlog --tag v0.1.1 jlog",
                     "- name: Install jlog v0.1.1, which the installer needs", "JLOG_VERSION: v0.1.1",
                     "# The tag v0.1.1 of jlog is the commit 8febdf1.", "cargo binstall jlog@0.1.1",
                     "curl -fsSL https://raw.githubusercontent.com/rahuldave/jlog/main/scripts/install.sh | sh -s -- --tag v0.1.1"):
            with self.subTest(line=line):
                self.assertEqual([version for _, version in jlog_pins({"a.yml": line})[0]], ["v0.1.1"])

    def test_the_scan_finds_an_install_without_a_pin_and_a_wrong_commit(self) -> None:
        for line in ("run: cargo install --git https://github.com/rahuldave/jlog jlog",
                     "run: cargo install --locked --git https://github.com/rahuldave/jlog --tag v0.2.0",
                     "run: cargo install --git https://github.com/rahuldave/jlog --rev 8febdf1 jlog",
                     "run: cargo install jlog --version 0.2.0",
                     "# The tag v0.5.0 of jlog is the commit abc1234.",
                     "curl -fsSL https://raw.githubusercontent.com/rahuldave/jlog/main/scripts/install.sh | sh -s -- --tag v0.5.0",
                     "curl -fsSL https://raw.githubusercontent.com/rahuldave/jlog/v0.5.0/scripts/install.sh | sh",
                     "curl -fsSL https://raw.githubusercontent.com/rahuldave/jlog/v0.2.0/scripts/install.sh | sh -s -- --tag v0.5.0",
                     "curl -fsSL https://raw.githubusercontent.com/rahuldave/jlog/224a622/scripts/install.sh | sh -s -- --tag v0.5.0",
                     "curl -fsSL https://github.com/rahuldave/jlog/raw/main/scripts/install.sh | sh",
                     "curl -fsSL https://raw.githubusercontent.com/rahuldave/jlog/refs/heads/main/scripts/install.sh | sh",
                     "curl -fsSLO https://github.com/rahuldave/jlog/releases/latest/download/jlog-x86_64-unknown-linux-musl.tar.gz",
                     "fetch jlog-v0.5.0-install.sh https://raw.githubusercontent.com/rahuldave/jlog/"
                     "1111111111111111111111111111111111111111/scripts/install.sh",
                     "curl -fsSL https://raw.githubusercontent.com/rahuldave/jlog/"
                     "224a622a27920256e3d6ad6a8363c9ea96078a20/scripts/install.sh | sh -s -- --tag v0.5.0",
                     "gh release download -R rahuldave/jlog"):
            with self.subTest(line=line):
                self.assertNotEqual(jlog_pins({"a.yml": line})[1], [])


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


def bare_env(**extra: str) -> dict[str, str]:
    """The environment without JNTERFACES_DIR and SKILL_PACKAGES_DIR, plus EXTRA. JNTERFACES_REPO names no repository
    unless EXTRA gives one, so no test clones jnterfaces from GitHub."""
    env = {k: v for k, v in os.environ.items() if k not in ("JNTERFACES_DIR", "SKILL_PACKAGES_DIR", "JNTERFACES_REPO")}
    return {**env, "JNTERFACES_REPO": "/nonexistent/jnterfaces", **extra}


def copy_checkout(dest: Path) -> None:
    """Copy the files of this checkout, committed or not, to DEST, as a fresh clone with the changes of the work."""
    files = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                           check=True, capture_output=True).stdout.decode().split("\0")
    for name in filter(None, files):
        source = ROOT / name
        if source.is_file():
            (dest / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest / name)


class FindJnterfacesTests(unittest.TestCase):
    """find_jnterfaces.sh takes JNTERFACES_DIR alone, else the sibling clone, the installed copy or a pinned clone."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve() / "a b"
        self.repo = base / "work" / "agent_gest_git_skills"
        (self.repo / "scripts").mkdir(parents=True)
        shutil.copy2(ROOT / "scripts/find_jnterfaces.sh", self.repo / "scripts")
        self.sibling = base / "work" / "jnterfaces"
        self.packages = base / "packages"
        self.installed = self.packages / "jnterfaces"
        self.home = base / "home"
        self.explicit = base / "mine"
        self.cache_home = base / "cache"
        # The upstream that a pinned clone comes from, with one commit that is the pin.
        self.upstream = self.fake(base / "upstream")
        git = ["git", "-C", str(self.upstream), "-c", "user.name=t", "-c", "user.email=t@example.com"]
        env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "start"]):
            subprocess.run(git + args, check=True, capture_output=True, env=env)
        self.pin = subprocess.run(git + ["rev-parse", "HEAD"], check=True, capture_output=True, text=True,
                                  env=env).stdout.strip()
        (self.repo / "scripts/jnterfaces_commit").write_text(self.pin + "\n")
        self.cache = self.cache_home / "agent_gest_git_skills" / self.pin / "jnterfaces"

    def fake(self, folder: Path, link_check: bool = True) -> Path:
        (folder / "scripts").mkdir(parents=True)
        (folder / "scripts/install_stack.py").write_text("")
        if link_check:
            (folder / "scripts/check_skill_links.py").write_text("")
        return folder

    def find(self, cwd: Path | None = None, **env: str) -> subprocess.CompletedProcess[str]:
        defaults = {"HOME": str(self.home), "XDG_CACHE_HOME": str(self.cache_home),
                    "JNTERFACES_REPO": str(self.upstream)}
        return subprocess.run([str(self.repo / "scripts/find_jnterfaces.sh"), "scripts/check_skill_links.py"],
                              capture_output=True, text=True, cwd=cwd, env=bare_env(**{**defaults, **env}))

    def found(self, **env: str) -> Path:
        run = self.find(**env)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(run.stdout.splitlines()), 1, run.stdout)
        return Path(run.stdout.strip())

    def test_jnterfaces_dir_wins(self) -> None:
        self.fake(self.sibling)
        self.assertEqual(self.found(JNTERFACES_DIR=str(self.fake(self.explicit))), self.explicit)

    def test_a_wrong_jnterfaces_dir_fails_and_tries_no_other_folder(self) -> None:
        self.fake(self.sibling)
        run = self.find(JNTERFACES_DIR=str(self.explicit))
        self.assertEqual(run.returncode, 1)
        self.assertIn(str(self.explicit), run.stderr)
        self.assertNotIn(str(self.sibling), run.stderr)
        self.assertFalse(self.cache.exists())

    def test_the_sibling_comes_before_the_installed_copy(self) -> None:
        self.fake(self.sibling)
        self.fake(self.installed)
        self.assertEqual(self.found(SKILL_PACKAGES_DIR=str(self.packages)), self.sibling)

    def test_a_sibling_without_the_file_fails_and_tries_no_other_clone(self) -> None:
        self.fake(self.sibling, link_check=False)
        self.fake(self.installed)
        run = self.find(SKILL_PACKAGES_DIR=str(self.packages))
        self.assertEqual(run.returncode, 1)
        self.assertIn(f"{self.sibling} has no scripts/check_skill_links.py", run.stderr)
        self.assertEqual(run.stdout, "")

    def test_without_a_sibling_the_installed_copy_is_found(self) -> None:
        self.fake(self.installed)
        self.assertEqual(self.found(SKILL_PACKAGES_DIR=str(self.packages)), self.installed)

    def test_the_installed_copy_is_in_the_home_folder_by_default(self) -> None:
        copy = self.fake(self.home / ".local/share/skill-packages/jnterfaces")
        self.assertEqual(self.found(), copy)

    def test_without_any_clone_the_pinned_commit_is_cloned_once(self) -> None:
        self.assertEqual(self.found(SKILL_PACKAGES_DIR=str(self.packages)), self.cache)
        head = subprocess.run(["git", "-C", str(self.cache), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
        self.assertEqual(head, self.pin)
        shutil.rmtree(self.upstream)
        self.assertEqual(self.found(SKILL_PACKAGES_DIR=str(self.packages)), self.cache)
        self.assertEqual([p.name for p in self.cache.parent.iterdir()], ["jnterfaces"])

    def test_a_failed_clone_fails_and_leaves_nothing(self) -> None:
        run = self.find(SKILL_PACKAGES_DIR=str(self.packages), JNTERFACES_REPO=str(self.home / "none"))
        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stdout, "")
        self.assertIn("Could not clone", run.stderr)
        self.assertIn("JNTERFACES_DIR", run.stderr)
        self.assertEqual(list(self.cache.parent.iterdir()), [])

    def test_a_cache_folder_that_is_no_clone_fails(self) -> None:
        self.cache.mkdir(parents=True)
        run = self.find(SKILL_PACKAGES_DIR=str(self.packages))
        self.assertEqual(run.returncode, 1)
        self.assertIn("Remove it", run.stderr)
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_cdpath_does_not_change_the_output(self) -> None:
        self.fake(self.explicit)
        run = self.find(cwd=self.explicit.parent, JNTERFACES_DIR="mine", CDPATH=".")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, f"{self.explicit}\n")
        # Called by a relative path, as the Justfile calls it, so the folder of the repository comes from CDPATH too.
        self.fake(self.sibling)
        run = subprocess.run(["scripts/find_jnterfaces.sh", "scripts/check_skill_links.py"], capture_output=True,
                             text=True, cwd=self.repo, env=bare_env(HOME=str(self.home), CDPATH="."))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, f"{self.sibling}\n")

    def test_an_unset_home_fails_with_a_message(self) -> None:
        env = {k: v for k, v in bare_env().items() if k not in ("HOME", "XDG_CACHE_HOME")}
        run = subprocess.run([str(self.repo / "scripts/find_jnterfaces.sh"), "scripts/check_skill_links.py"],
                             capture_output=True, text=True, env=env)
        self.assertEqual(run.returncode, 1)
        self.assertIn("HOME is not set", run.stderr)

    def test_a_clone_never_asks_for_a_user_name(self) -> None:
        trace = self.home / "env"
        bin_dir = self.home / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "git").write_text(f'#!/bin/sh\nprintf "%s" "$GIT_TERMINAL_PROMPT" > "{trace}"\nexit 128\n')
        (bin_dir / "git").chmod(0o755)
        run = self.find(SKILL_PACKAGES_DIR=str(self.packages), PATH=f"{bin_dir}:{os.environ['PATH']}")
        self.assertEqual(run.returncode, 1)
        self.assertEqual(trace.read_text(), "0")

    def test_a_failed_rename_fails_with_a_message(self) -> None:
        bin_dir = self.home / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "uv").write_text("#!/bin/sh\nexit 1\n")
        (bin_dir / "uv").chmod(0o755)
        run = self.find(SKILL_PACKAGES_DIR=str(self.packages), PATH=f"{bin_dir}:{os.environ['PATH']}")
        self.assertEqual(run.returncode, 1)
        self.assertIn("Could not rename", run.stderr)
        self.assertEqual(list(self.cache.parent.iterdir()), [])


class OutsideProjectsTests(unittest.TestCase):
    """The link check of just lint passes in a clone with no sibling jnterfaces, and JNTERFACES_DIR unset."""

    def test_the_link_check_finds_the_installed_copy(self) -> None:
        found = subprocess.run([str(ROOT / "scripts/find_jnterfaces.sh"), "scripts/check_skill_links.py"],
                               capture_output=True, text=True, check=True).stdout.strip()
        with tempfile.TemporaryDirectory() as tmp:
            clone = Path(tmp) / "elsewhere" / "agent_gest_git_skills"
            copy_checkout(clone)
            self.assertFalse((clone.parent / "jnterfaces").exists())
            packages = Path(tmp) / "packages"
            packages.mkdir()
            (packages / "jnterfaces").symlink_to(found)
            files = [str(clone / "AGENTS.template.md"), str(clone / ".agents/skills/gtw/SKILL.md")]
            run = subprocess.run([str(clone / "scripts/check_skill_links.sh"), *files], capture_output=True,
                                 text=True, cwd=clone, env=bare_env(SKILL_PACKAGES_DIR=str(packages)))
            self.assertEqual(run.returncode, 0, run.stderr)
            run = subprocess.run([str(clone / "scripts/check_skill_links.sh"), *files], capture_output=True,
                                 text=True, cwd=clone, env=bare_env(SKILL_PACKAGES_DIR=str(Path(tmp) / "none"),
                                                                    XDG_CACHE_HOME=str(Path(tmp) / "cache"),
                                                                    JNTERFACES_REPO=str(Path(tmp) / "no-repo")))
            self.assertEqual(run.returncode, 1)
            self.assertIn("Could not clone", run.stderr)


if __name__ == "__main__":
    unittest.main()
