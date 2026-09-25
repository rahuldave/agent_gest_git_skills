"""Focused regression tests for source and npx installation safety."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / 'target'
        self.target.mkdir()

    def run_install(self, *options, success=True):
        run = subprocess.run(['bash', str(ROOT / 'scripts/install.sh'), *options, str(self.target)], capture_output=True, text=True)
        if success:
            self.assertEqual(run.returncode, 0, run.stderr)
        else:
            self.assertNotEqual(run.returncode, 0)
        return run

    def test_preserves_existing_settings_and_agents_on_repeat(self):
        (self.target / 'AGENTS.md').write_text('my guidance\n')
        claude = self.target / '.claude/settings.json'
        claude.parent.mkdir()
        claude.write_text(json.dumps({'permissions': {'allow': ['Read']}, 'hooks': {'SessionStart': [
            {'hooks': [{'type': 'command', 'command': 'echo other'}]}
        ]}}))
        codex = self.target / '.codex/hooks.json'
        codex.parent.mkdir()
        codex.write_text(json.dumps({'custom': True, 'hooks': {'Stop': [
            {'hooks': [{'type': 'command', 'command': 'echo codex'}]}
        ]}}))
        self.run_install()
        first = (claude.read_bytes(), codex.read_bytes())
        self.run_install()
        self.assertEqual(first, (claude.read_bytes(), codex.read_bytes()))
        self.assertEqual((self.target / 'AGENTS.md').read_text(), 'my guidance\n')
        c = json.loads(claude.read_text())
        self.assertEqual(c['permissions']['allow'], ['Read'])
        self.assertEqual(sum(h['command'] == 'echo other' for g in c['hooks']['SessionStart'] for h in g['hooks']), 1)
        x = json.loads(codex.read_text())
        self.assertTrue(x['custom'])
        self.assertEqual(sum(h['command'] == 'echo codex' for g in x['hooks']['Stop'] for h in g['hooks']), 1)
        provenance = json.loads((self.target / '.agents/gest-git-install.json').read_text())
        self.assertEqual(provenance['source_revision'], subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip())
        self.assertTrue(provenance['source_worktree_dirty'])

    def test_invalid_settings_cause_no_partial_install(self):
        bad = self.target / '.codex/hooks.json'
        bad.parent.mkdir()
        bad.write_text('{oops')
        self.assertIn('Invalid JSON', self.run_install(success=False).stderr)
        self.assertFalse((self.target / '.claude/settings.json').exists())
        self.assertFalse((self.target / '.agents/gest-git-install.json').exists())
        self.assertEqual(bad.read_text(), '{oops')

    def test_conflict_causes_no_partial_install(self):
        path = self.target / '.claude/settings.json'
        path.parent.mkdir()
        source = json.loads((ROOT / '.claude/settings.json').read_text())
        source['hooks']['SessionStart'][0]['hooks'][0]['timeout'] = 42
        path.write_text(json.dumps(source))
        self.assertIn('Conflicting hook command', self.run_install(success=False).stderr)
        self.assertFalse((self.target / '.codex/hooks.json').exists())

    def test_existing_hook_script_collision_is_preserved(self):
        path = self.target / '.claude/hooks/session-start.sh'
        path.parent.mkdir(parents=True)
        path.write_text('# custom\n')
        self.assertIn('Existing hook script differs', self.run_install(success=False).stderr)
        self.assertEqual(path.read_text(), '# custom\n')

    def test_pinned_commit_excludes_dirty_source(self):
        commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
        self.run_install('--source-commit', commit)
        metadata = json.loads((self.target / '.agents/gest-git-install.json').read_text())
        self.assertEqual(metadata['source_revision'], commit)
        self.assertFalse(metadata['source_worktree_dirty'])
        self.assertEqual(metadata['source_requested_commit'], commit)

    def test_bundled_installer_uses_local_pinned_source(self):
        commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
        import os
        env = dict(os.environ, AGENT_GEST_GIT_SKILLS_SOURCE=str(ROOT), AGENT_GEST_GIT_SKILLS_COMMIT=commit)
        run = subprocess.run(['bash', str(ROOT / '.agents/skills/gest_git_installer/scripts/install_gest_git_package.sh'), str(self.target)], capture_output=True, text=True, env=env)
        self.assertEqual(run.returncode, 0, run.stderr)
        metadata = json.loads((self.target / '.agents/gest-git-install.json').read_text())
        self.assertEqual(metadata['source_revision'], commit)

    def test_sync_hooks_merges(self):
        self.run_install()
        codex = self.target / '.codex/hooks.json'
        value = json.loads(codex.read_text())
        value['another'] = 'keep'
        codex.write_text(json.dumps(value))
        run = subprocess.run(['bash', str(ROOT / 'scripts/sync_g_skills.sh'), '--hooks', str(self.target)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(codex.read_text())['another'], 'keep')


if __name__ == '__main__':
    unittest.main()
