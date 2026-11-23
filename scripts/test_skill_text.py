"""The skills run the checks through the recipes, so they name no tool of a language, and each one that needs the
recipes tells the agent to run gsu when they are missing."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".agents/skills"
# The skills of the table "The skills" of docs/specs/commit-gates.md that need `just check`.
NEED_RECIPES = ("gfm", "gdo", "gim", "gte", "grv", "gcm", "gpa", "gor")
# The skills that tell an agent what to run in a fix round, the pass of fixes after the findings of a review.
FIX_ROUNDS = ("gcm", "gim", "gte", "grv", "gfm")
LANGUAGE_TOOLS = re.compile(r"\b(ruff|biome|pytest|mypy|pyright|eslint|prettier|clippy|rustfmt|vitest|jest|tsc)\b"
                            r"|\bcargo (fmt|clippy|test|check)\b", re.IGNORECASE)


class SkillTextTests(unittest.TestCase):
    def test_each_skill_that_needs_the_recipes_says_to_run_gsu_without_them(self) -> None:
        for name in NEED_RECIPES:
            with self.subTest(skill=name):
                text = " ".join((SKILLS / name / "SKILL.md").read_text().split())
                self.assertIn("When the repository has no `just check`, run `gsu` first.", text)

    def test_each_skill_of_a_fix_round_says_just_quick_and_just_check_on_the_final_tree(self) -> None:
        for name in FIX_ROUNDS:
            with self.subTest(skill=name):
                text = " ".join((SKILLS / name / "SKILL.md").read_text().split())
                self.assertRegex(text, r"run `just quick` (when|instead)")
                self.assertRegex(text, r"`just check` (once|again after the last change)")
                self.assertNotIn("`just check` after each change", text)
        gcm = " ".join((SKILLS / "gcm" / "SKILL.md").read_text().split())
        self.assertIn("Run `just check` last, on the tree that you commit. The gate needs a pass for that tree", gcm)

    def test_no_skill_names_a_tool_of_a_language(self) -> None:
        for path in sorted(SKILLS.glob("g*/**/*.md")):
            with self.subTest(path=str(path.relative_to(ROOT))):
                found = [m.group(0) for m in LANGUAGE_TOOLS.finditer(path.read_text())]
                self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
