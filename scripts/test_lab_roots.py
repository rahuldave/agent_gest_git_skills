"""The lab scripts run rm -rf on their lab root, so a root that could leave the temp folder must stop them first."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "scripts/run_tag_dependency_typescript_lab.sh"


class LabRootTests(unittest.TestCase):
    def test_a_root_with_a_dot_part_or_outside_the_temp_folder_stops_before_any_change(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent-gest-keep-") as keep:
            # The folder that a traversal would reach. It must still be there after each run.
            marker = Path(keep) / "marker"
            marker.write_text("keep\n")
            roots = (
                f"/private/tmp/..{keep}",
                f"/tmp/agent-gest-git-tutorial/../..{keep}",
                f"/tmp/agent-gest-x/./{Path(keep).name}",
                str(Path.home() / "agent-gest-lab"),
            )
            for root in roots:
                with self.subTest(root=root):
                    run = subprocess.run(["bash", str(LAB), root, f"{keep}/log"], capture_output=True, text=True)
                    self.assertEqual(run.returncode, 1, run.stderr)
                    self.assertIn("refusing", run.stderr)
                    self.assertTrue(marker.exists())

    def test_a_root_through_a_link_stops_before_any_change(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent-gest-links-", dir="/tmp") as base, \
                tempfile.TemporaryDirectory(prefix="keep-") as keep:
            marker = Path(keep) / "lab" / "marker"
            marker.parent.mkdir()
            marker.write_text("keep\n")
            # A planted link inside the temp folder, as anyone can make in /tmp, to a folder outside it.
            (Path(base) / "agent-gest-tutorial").symlink_to(keep)
            (Path(base) / "agent-gest-lab").symlink_to(marker.parent)
            for root in (f"{base}/agent-gest-tutorial/lab", f"{base}/agent-gest-lab",
                         f"{base}/agent-gest-tutorial/new/deeper"):
                with self.subTest(root=root):
                    run = subprocess.run(["bash", str(LAB), root, f"{base}/log"], capture_output=True, text=True)
                    self.assertEqual(run.returncode, 1, run.stderr)
                    self.assertIn("refusing", run.stderr)
                    self.assertTrue(marker.exists())


if __name__ == "__main__":
    unittest.main()
