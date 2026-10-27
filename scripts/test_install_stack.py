"""Tests for scripts/install_stack.sh, which installs this package, jnterfaces and optional sklanes together."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'scripts/install_stack.sh'
FAKE_INSTALLER = '''#!/usr/bin/env bash
# Log the call; on a real run, write a record as a package installer does.
printf '%s %s\\n' "{name}" "$*" >> "$STACK_LOG"
[ -n "${{FAIL_DRY_RUN:-}}" ] && [ "$FAIL_DRY_RUN" = "{name}" ] && exit 1
for arg in "$@"; do [ "$arg" = --dry-run ] && exit 0; done
target="${{@: -1}}"
mkdir -p "$target/.agents"
echo '{{"source_revision": "rev-{name}"}}' > "$target/.agents/{name}-install.json"
'''


def git(path, *args):
    subprocess.run(['git', '-C', str(path), '-c', 'user.name=T', '-c', 'user.email=t@example.invalid', *args],
                   check=True, capture_output=True)


class StackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.target = self.base / 'target'
        self.target.mkdir()
        self.log = self.base / 'log'
        self.gest = self.fake('agent_gest_git_skills', with_stack=True)
        self.jnterfaces = self.fake('jnterfaces')
        self.sklanes = self.fake('sklanes')

    def fake(self, name, with_stack=False):
        root = self.base / name
        (root / 'scripts').mkdir(parents=True)
        (root / 'skill-package.json').write_text(json.dumps({'repository': {'name': name}}))
        installer = root / 'scripts/install.sh'
        installer.write_text(FAKE_INSTALLER.format(name=name))
        installer.chmod(0o755)
        if with_stack:
            (root / 'scripts/install_stack.sh').write_bytes(STACK.read_bytes())
        git(root, 'init', '-q')
        git(root, 'add', '-A')
        git(root, 'commit', '-q', '-m', 'fake')
        return root

    def stack(self, *args, env=None):
        return subprocess.run(['bash', self.gest / 'scripts/install_stack.sh', self.target, *args],
                              capture_output=True, text=True, env=dict(os.environ, STACK_LOG=str(self.log), **(env or {})))

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_installs_gest_and_jnterfaces_after_a_dry_run_of_each(self):
        run = self.stack()
        self.assertEqual(run.returncode, 0, run.stderr)
        names = [line.split()[0] for line in self.calls()]
        self.assertEqual(names, ['agent_gest_git_skills', 'jnterfaces'] * 2)
        self.assertTrue(all('--dry-run' in line for line in self.calls()[:2]))
        self.assertFalse(any('--dry-run' in line for line in self.calls()[2:]))
        self.assertEqual(sorted(p.name for p in (self.target / '.agents').iterdir()),
                         ['agent_gest_git_skills-install.json', 'jnterfaces-install.json'])
        self.assertIn('rev-jnterfaces', run.stdout)

    def test_with_lanes_adds_sklanes(self):
        run = self.stack('--with-lanes')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue((self.target / '.agents/sklanes-install.json').is_file())

    def test_a_failed_dry_run_writes_nothing(self):
        run = self.stack('--with-lanes', env={'FAIL_DRY_RUN': 'sklanes'})
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse((self.target / '.agents').exists())

    def test_dry_run_writes_nothing(self):
        run = self.stack('--with-lanes', '--dry-run')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse((self.target / '.agents').exists())
        self.assertEqual(len(self.calls()), 3)

    def test_missing_or_wrong_clone_stops_before_any_install(self):
        run = self.stack('--jnterfaces', self.base / 'nowhere')
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('No jnterfaces clone', run.stderr)
        run = self.stack('--jnterfaces', self.sklanes)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('is not the jnterfaces package', run.stderr)
        self.assertEqual(self.calls(), [])

    def test_clean_pins_each_package_to_its_head(self):
        self.assertEqual(self.stack('--clean', '--dry-run').returncode, 0)
        for line in self.calls():
            name = line.split()[0]
            head = subprocess.check_output(['git', '-C', str(self.base / name), 'rev-parse', 'HEAD'], text=True).strip()
            self.assertIn(f'--source-commit {head}', line)

    def test_real_sibling_packages_when_present(self):
        jnterfaces, sklanes = ROOT.parent / 'jnterfaces', ROOT.parent / 'sklanes'
        if not (jnterfaces / 'scripts/install.sh').is_file() or not (sklanes / 'scripts/install.sh').is_file():
            self.skipTest('no jnterfaces and sklanes clones next to this repository')
        run = subprocess.run(['bash', STACK, self.target, '--with-lanes'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        for name in ('gest-git', 'jnterfaces', 'sklanes'):
            record = json.loads((self.target / f'.agents/{name}-install.json').read_text())
            self.assertRegex(record['source_revision'], '^[0-9a-f]{40}$')
        for skill in ('gsu', 'just', 'jagt-protocol', 'cx', 'lanes'):
            self.assertTrue((self.target / f'.agents/skills/{skill}/SKILL.md').is_file(), skill)


    def test_double_dash_allows_a_target_that_starts_with_a_dash(self):
        odd = self.base / '-odd'
        odd.mkdir()
        run = subprocess.run(['bash', self.gest / 'scripts/install_stack.sh', '--dry-run', '--', '-odd'],
                             capture_output=True, text=True, cwd=self.base, env=dict(os.environ, STACK_LOG=str(self.log)))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(all(line.endswith(str(odd.resolve())) for line in self.calls()))


if __name__ == '__main__':
    unittest.main()
