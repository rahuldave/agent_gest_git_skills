"""Offline regressions for live-lab repository ownership and cleanup."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "scripts/run_gitbutler_github_integration_lab.sh"


class LiveLabCleanupTests(unittest.TestCase):
    def run_stubbed_lab(self, create_result: str) -> tuple[subprocess.CompletedProcess[str], list[str], Path, Path]:
        # The stub never contacts GitHub. Its event log is outside the lab's
        # owned directory, so cleanup cannot erase the evidence.
        scratch = tempfile.TemporaryDirectory(prefix="gest-live-cleanup-test-")
        self.addCleanup(scratch.cleanup)
        base = Path(scratch.name)
        bin_dir = base / "bin"
        bin_dir.mkdir()
        events = base / "gh-events.txt"
        sentinel = base / "pre-existing-repo.txt"
        sentinel.write_text("belongs to another run\n")
        gh = bin_dir / "gh"
        gh.write_text("""#!/usr/bin/env bash
set -eu
case "$1 $2" in
  'auth status') echo 'Token scopes: repo, delete_repo' ;;
  'repo create')
    printf 'create %s\\n' "$3" >> "$GH_STUB_EVENTS"
    [ "$GH_STUB_CREATE_RESULT" = success ] || exit 1
    ;;
  'repo delete') printf 'delete %s\\n' "$3" >> "$GH_STUB_EVENTS" ;;
  *) echo "unexpected gh call: $*" >&2; exit 90 ;;
esac
""")
        gh.chmod(0o755)
        but = bin_dir / "but"
        but.write_text("#!/usr/bin/env bash\nexit 91\n")
        but.chmod(0o755)
        lab_root = base / "lab"
        env = os.environ.copy()
        env.update(
            PATH=f"{bin_dir}:{env['PATH']}",
            GH_STUB_EVENTS=str(events),
            GH_STUB_CREATE_RESULT=create_result,
            AGENT_GEST_GITBUTLER_GITHUB_OWNER="test-owner",
            AGENT_GEST_GITBUTLER_GITHUB_RUN_ID="ownership-test",
            AGENT_GEST_GITBUTLER_GITHUB_LAB=str(lab_root),
        )
        result = subprocess.run(["bash", str(LAB)], cwd=ROOT, env=env, text=True, capture_output=True)
        return result, events.read_text().splitlines(), sentinel, lab_root

    def test_collision_never_deletes_preexisting_repo(self) -> None:
        result, events, sentinel, lab_root = self.run_stubbed_lab("collision")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(events, ["create test-owner/agent-gest-gitbutler-live-ownership-test-plain-branch"])
        self.assertEqual(sentinel.read_text(), "belongs to another run\n")
        self.assertFalse((lab_root / "plain-branch").exists())

    def test_successfully_created_repo_is_deleted_after_later_failure(self) -> None:
        result, events, sentinel, lab_root = self.run_stubbed_lab("success")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        name = "test-owner/agent-gest-gitbutler-live-ownership-test-plain-branch"
        self.assertEqual(events, [f"create {name}", f"delete {name}"])
        self.assertEqual(sentinel.read_text(), "belongs to another run\n")
        self.assertFalse((lab_root / "plain-branch").exists())


if __name__ == "__main__":
    unittest.main()
