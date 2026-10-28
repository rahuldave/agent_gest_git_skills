"""Tests for scripts/install_stack.sh, which passes the old options to the stack installer of jnterfaces."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'scripts/install_stack.sh'
FAKE_STACK = '''#!/usr/bin/env bash
# Log each argument on its own line.
printf '%s\\n' "$@" > "$STACK_LOG"
'''


class WrapperTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.target = self.base / 'target'
        self.target.mkdir()
        self.log = self.base / 'log'
        self.jnterfaces = self.base / 'jnterfaces'
        (self.jnterfaces / 'scripts').mkdir(parents=True)
        (self.jnterfaces / 'scripts/install_stack.sh').write_text(FAKE_STACK)

    def stack(self, *args, cwd=None):
        return subprocess.run(['bash', STACK, *args], capture_output=True, text=True, cwd=cwd,
                              env=dict(os.environ, STACK_LOG=str(self.log)))

    def forwarded(self):
        return self.log.read_text().splitlines()

    def test_a_target_without_saved_choices_gets_the_old_set(self):
        run = self.stack(self.target, '--jnterfaces', self.jnterfaces)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.forwarded(), [str(self.target.resolve()), '--clone', f'agent_gest_git_skills={ROOT}',
                                            '--with', 'gest,cx,jagt-protocol', '--without', 'nossaifd'])
        self.assertIn('the stack installer is now', run.stderr)

    def test_saved_choices_win_over_the_old_set(self):
        (self.target / '.agents').mkdir()
        (self.target / '.agents/stack.json').write_text('{"version": 1, "choices": {"cx": false}}')
        run = self.stack(self.target, '--jnterfaces', self.jnterfaces)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.forwarded()[1:], ['--clone', f'agent_gest_git_skills={ROOT}'])

    def test_choice_options_win_over_the_old_set(self):
        for option in (['--without', 'cx'], ['--with', 'sklanes'], ['--all'], ['--defaults'], ['--ask']):
            run = self.stack(self.target, '--jnterfaces', self.jnterfaces, *option)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(self.forwarded()[3:], option, option)

    def test_translates_the_old_options(self):
        run = self.stack('--with-lanes', '--sklanes', '/x/sk', '--clean', '--dry-run',
                         '--jnterfaces', self.jnterfaces, self.target)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.forwarded()[3:], ['--with', 'sklanes', '--clone', 'sklanes=/x/sk', '--clean', '--dry-run',
                                                '--with', 'gest,cx,jagt-protocol', '--without', 'nossaifd'])

    def test_a_symlinked_target_is_refused(self):
        link = self.base / 'link'
        link.symlink_to(self.target)
        for path in (str(link), f'{link}/', f'{link}//'):
            run = self.stack(path, '--jnterfaces', self.jnterfaces)
            self.assertEqual(run.returncode, 2, path)
            self.assertIn('must not be a symlink', run.stderr)
        self.assertFalse(self.log.exists())

    def test_an_installed_nossaifd_stays_on(self):
        (self.target / '.agents').mkdir()
        (self.target / '.agents/nossaifd-install.json').write_text('{}')
        run = self.stack(self.target, '--jnterfaces', self.jnterfaces)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.forwarded()[3:], ['--with', 'gest,cx,jagt-protocol'])

    def test_double_dash_allows_a_target_that_starts_with_a_dash(self):
        odd = self.base / '-odd'
        odd.mkdir()
        run = self.stack('--jnterfaces', self.jnterfaces, '--', '-odd', cwd=self.base)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.forwarded()[0], str(odd.resolve()))

    def test_a_missing_jnterfaces_clone_says_how_to_get_one(self):
        run = self.stack(self.target, '--jnterfaces', self.base / 'nowhere')
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('git', run.stderr.lower())
        self.assertIn('https://github.com/rahuldave/jnterfaces', run.stderr)
        self.assertFalse(self.log.exists())

    def test_usage_errors(self):
        self.assertEqual(self.stack().returncode, 2)
        self.assertEqual(self.stack(self.target, self.base).returncode, 2)
        self.assertEqual(self.stack(self.target, '--jnterfaces').returncode, 2)

    def test_real_jnterfaces_when_present(self):
        # CI clones jnterfaces and nossaifd into one folder and sets JNTERFACES_DIR.
        jnterfaces = Path(os.environ.get('JNTERFACES_DIR', ROOT.parent / 'jnterfaces'))
        if not (jnterfaces / 'scripts/install_stack.py').is_file():
            self.skipTest('no jnterfaces clone with the stack installer; set JNTERFACES_DIR')
        subprocess.run(['git', 'init', '-q', str(self.target)], check=True)
        run = subprocess.run(['bash', STACK, self.target, '--jnterfaces', jnterfaces], capture_output=True, text=True,
                             stdin=subprocess.DEVNULL)
        self.assertEqual(run.returncode, 0, run.stderr)
        for skill in ('gtw', 'just', 'cx', 'jagt-protocol'):
            self.assertTrue((self.target / f'.agents/skills/{skill}/SKILL.md').is_file(), skill)
        self.assertFalse((self.target / '.agents/skills/nossaifd').exists())
        # A later run keeps the saved choices: here, cx turned off stays off.
        run = subprocess.run(['bash', STACK, self.target, '--jnterfaces', jnterfaces, '--without', 'cx'],
                             capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(run.returncode, 0, run.stderr)
        run = subprocess.run(['bash', STACK, self.target, '--jnterfaces', jnterfaces], capture_output=True, text=True,
                             stdin=subprocess.DEVNULL)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse((self.target / '.agents/skills/cx').exists())
        record = json.loads((self.target / '.agents/gest-git-install.json').read_text())
        self.assertRegex(record['source_revision'], '^[0-9a-f]{40}$')


if __name__ == '__main__':
    unittest.main()
