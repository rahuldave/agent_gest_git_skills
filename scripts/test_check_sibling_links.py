"""Tests for scripts/check_sibling_links.py."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_sibling_links import problems  # noqa: E402


class SiblingLinkTests(unittest.TestCase):
    def test_each_paragraph_needs_its_own_fallback(self):
        text = ('Read `.agents/skills/just/SKILL.md` of jnterfaces when it is installed.\n\n'
                'Then read `.agents/skills/cx/SKILL.md` of jnterfaces.\n')
        found = problems('f.md', text)
        self.assertEqual(len(found), 1)
        self.assertIn('cx/SKILL.md', found[0])

    def test_fallback_may_wrap_across_lines(self):
        self.assertEqual(problems('f.md', 'Read `.agents/skills/just/SKILL.md`. If jnterfaces\nis not installed, use AGENTS.md.\n'), [])

    def test_paths_and_folders_must_exist_in_jnterfaces(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / '.agents/skills/cx/references').mkdir(parents=True)
            (root / '.agents/skills/cx/SKILL.md').write_text('x')
            ok = 'See `.agents/skills/cx/SKILL.md` and `.agents/skills/cx/references/` of jnterfaces, when it is installed.'
            self.assertEqual(problems('f.md', ok, root), [])
            bad = 'See `.agents/skills/cx/NOPE.md` and `.agents/skills/just/` of jnterfaces, when it is installed.'
            self.assertEqual(len(problems('f.md', bad, root)), 2)


    def test_boundaries_traversal_and_the_package_name(self):
        self.assertEqual(problems('f.md', 'See `.agents/skills/justice/x.md`.'), [])
        self.assertEqual(problems('f.md', 'https://example.org/master/skills/just/SKILL.md'), [])
        self.assertEqual(len(problems('f.md', 'See `skills/just/SKILL.md`.')), 1)
        self.assertEqual(len(problems('f.md', 'See `.agents/skills/cx/SKILL.md` when it is installed.')), 1)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / '.agents/skills/just').mkdir(parents=True)
            (root / 'README.md').write_text('x')
            text = 'See `.agents/skills/just/../../../README.md` when jnterfaces is installed.'
            self.assertEqual(len(problems('f.md', text, root)), 1)


if __name__ == '__main__':
    unittest.main()
