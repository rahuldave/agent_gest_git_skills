"""`just --list` shows only the last comment line above a recipe, so the doc of each recipe of the role is one line,
with a blank line between it and any longer comment above it."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / ".agents/just/roles/agent_gest_git_skills.just"


@unittest.skipUnless(shutil.which("just"), "needs just")
class RecipeDocTests(unittest.TestCase):
    def test_the_doc_of_each_recipe_is_its_whole_comment(self) -> None:
        dump = subprocess.run(["just", "--justfile", str(ROLE), "--dump", "--dump-format", "json"], check=True,
                              capture_output=True, text=True).stdout
        recipes = json.loads(dump)["recipes"]
        lines = ROLE.read_text().splitlines()
        for name, recipe in recipes.items():
            with self.subTest(recipe=name):
                self.assertTrue(recipe["doc"], "no doc comment")
                self.assertIn(f"# {recipe['doc']}", lines, "the doc is not a comment line, such as a [doc] attribute")
                doc = lines.index(f"# {recipe['doc']}")
                self.assertFalse(lines[doc - 1].startswith("#"), "the comment above the doc goes on, so just "
                                 "--list shows only its last line; put a blank line between them")

    def test_ci_gate_is_a_step_of_just_check_that_logs_its_end(self) -> None:
        # The index of jnterfaces puts ci-gate in just check, and jlog pass needs the last line jlog step ci-gate.
        dump = subprocess.run(["just", "--justfile", str(ROLE), "--dump", "--dump-format", "json"], check=True,
                              capture_output=True, text=True).stdout
        body = json.loads(dump)["recipes"]["ci-gate"]["body"]
        self.assertEqual(["".join(part for part in body[-1] if isinstance(part, str))], ["jlog step ci-gate"])
        self.assertIn("--trailers", json.dumps(body[0]))


if __name__ == "__main__":
    unittest.main()
