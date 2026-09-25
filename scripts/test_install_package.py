"""Focused regression tests for safe package installation."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATHS = (
    'scripts/install.sh', 'scripts/install_package.py', 'scripts/sync_g_skills.sh',
    '.agents/skills/gest_git_installer/SKILL.md',
    '.agents/skills/gest_git_installer/scripts/install_gest_git_package.sh',
)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.target = base / 'target'
        self.target.mkdir()
        self.source = base / 'source'
        subprocess.run(['git', 'clone', '--quiet', str(ROOT), str(self.source)], check=True)
        for relative in INSTALLER_PATHS:
            destination = self.source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        subprocess.run(['git', '-C', str(self.source), 'add', *INSTALLER_PATHS], check=True)
        staged = subprocess.run(['git', '-C', str(self.source), 'diff', '--cached', '--quiet'])
        if staged.returncode:
            subprocess.run(['git', '-C', str(self.source), '-c', 'user.name=Test',
                            '-c', 'user.email=test@example.invalid', 'commit', '--quiet',
                            '-m', 'test: capture installer under test'], check=True)
        self.commit = subprocess.check_output(['git', '-C', str(self.source), 'rev-parse', 'HEAD'], text=True).strip()
        self.assertEqual(self.status(), '')

    def status(self):
        return subprocess.check_output(['git', '-C', str(self.source), 'status', '--porcelain',
                                        '--untracked-files=all'], text=True).strip()

    def run_install(self, *options, success=True):
        run = subprocess.run(['bash', str(self.source / 'scripts/install.sh'), *options,
                              str(self.target)], capture_output=True, text=True)
        self.assertEqual(run.returncode == 0, success, run.stderr)
        return run

    def provenance(self):
        return json.loads((self.target / '.agents/gest-git-install.json').read_text())

    def test_clean_source_and_repeat_preserve_existing_settings_and_agents(self):
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
        self.assertEqual(json.loads(claude.read_text())['permissions']['allow'], ['Read'])
        self.assertEqual(sum(h['command'] == 'echo other' for g in json.loads(claude.read_text())['hooks']['SessionStart'] for h in g['hooks']), 1)
        self.assertTrue(json.loads(codex.read_text())['custom'])
        self.assertEqual(self.provenance()['source_revision'], self.commit)
        self.assertFalse(self.provenance()['source_worktree_dirty'])
        self.assertFalse(self.provenance()['source_checkout_dirty'])

    def test_dirty_source_installs_exact_dirty_bytes_and_records_status(self):
        skill = self.source / '.agents/skills/gbs/SKILL.md'
        skill.write_bytes(skill.read_bytes() + b'\nDIRTY_SKILL_MARKER\n')
        self.run_install()
        self.assertEqual((self.target / '.agents/skills/gbs/SKILL.md').read_bytes(), skill.read_bytes())
        self.assertTrue(self.provenance()['source_worktree_dirty'])
        self.assertTrue(self.provenance()['source_checkout_dirty'])
        self.assertEqual(self.provenance()['source_revision'], self.commit)

    def test_pinned_dirty_source_installs_committed_bytes(self):
        skill = self.source / '.agents/skills/gbs/SKILL.md'
        committed = skill.read_bytes()
        skill.write_bytes(committed + b'\nDIRTY_SKILL_MARKER\n')
        self.run_install('--source-commit', self.commit)
        self.assertEqual((self.target / '.agents/skills/gbs/SKILL.md').read_bytes(), committed)
        metadata = self.provenance()
        self.assertEqual(metadata['source_revision'], self.commit)
        self.assertFalse(metadata['source_worktree_dirty'])
        self.assertTrue(metadata['source_checkout_dirty'])
        self.assertEqual(metadata['source_requested_commit'], self.commit)

    def test_existing_skill_file_collision_is_preserved_and_preflighted(self):
        skill = self.target / '.agents/skills/gbs/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('local custom skill\n')
        self.assertIn('Existing managed file differs', self.run_install(success=False).stderr)
        self.assertEqual(skill.read_text(), 'local custom skill\n')
        self.assertFalse((self.target / '.claude/settings.json').exists())
        self.assertFalse((self.target / '.agents/gest-git-install.json').exists())

    def test_modified_managed_skill_blocks_refresh(self):
        self.run_install()
        skill = self.target / '.agents/skills/gbs/SKILL.md'
        skill.write_text('local changed skill\n')
        self.assertIn('Existing managed file differs', self.run_install(success=False).stderr)
        self.assertEqual(skill.read_text(), 'local changed skill\n')

    def test_invalid_settings_cause_no_partial_install(self):
        bad = self.target / '.codex/hooks.json'
        bad.parent.mkdir()
        bad.write_text('{oops')
        self.assertIn('Invalid JSON', self.run_install(success=False).stderr)
        self.assertFalse((self.target / '.claude/settings.json').exists())
        self.assertFalse((self.target / '.agents/gest-git-install.json').exists())
        self.assertEqual(bad.read_text(), '{oops')

    def test_hook_command_conflict_causes_no_partial_install(self):
        path = self.target / '.claude/settings.json'
        path.parent.mkdir()
        source = json.loads((self.source / '.claude/settings.json').read_text())
        source['hooks']['SessionStart'][0]['hooks'][0]['timeout'] = 42
        path.write_text(json.dumps(source))
        self.assertIn('Conflicting hook command', self.run_install(success=False).stderr)
        self.assertFalse((self.target / '.codex/hooks.json').exists())

    def test_existing_hook_script_collision_is_preserved(self):
        path = self.target / '.claude/hooks/session-start.sh'
        path.parent.mkdir(parents=True)
        path.write_text('# custom\n')
        self.assertIn('Existing managed file differs', self.run_install(success=False).stderr)
        self.assertEqual(path.read_text(), '# custom\n')

    def test_target_symlinked_skill_path_cannot_write_outside(self):
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        (self.target / '.agents').symlink_to(outside, target_is_directory=True)
        self.assertIn('Symlinked managed path', self.run_install(success=False).stderr)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.target / '.claude/settings.json').exists())

    def test_target_npx_style_skill_symlink_cannot_write_outside(self):
        outside = Path(self.temp.name) / 'linked-skill'
        outside.mkdir()
        (outside / 'SKILL.md').write_text('external skill\n')
        skill = self.target / '.agents/skills/gbs'
        skill.parent.mkdir(parents=True)
        skill.symlink_to(outside, target_is_directory=True)
        self.assertIn('Symlinked managed path', self.run_install(success=False).stderr)
        self.assertEqual((outside / 'SKILL.md').read_text(), 'external skill\n')
        self.assertFalse((self.target / '.claude/settings.json').exists())

    def test_target_symlinked_settings_cannot_write_outside(self):
        outside = Path(self.temp.name) / 'outside-settings.json'
        outside.write_text('{"original": true}\n')
        setting = self.target / '.claude/settings.json'
        setting.parent.mkdir()
        setting.symlink_to(outside)
        self.assertIn('Symlinked managed path', self.run_install(success=False).stderr)
        self.assertEqual(outside.read_text(), '{"original": true}\n')
        self.assertFalse((self.target / '.agents/gest-git-install.json').exists())

    def test_source_symlinked_skill_directory_is_rejected(self):
        original = self.source / '.agents/skills/gbs'
        outside = Path(self.temp.name) / 'outside-source'
        original.rename(outside)
        original.symlink_to(outside, target_is_directory=True)
        self.assertIn('Symlinked managed path', self.run_install(success=False).stderr)
        self.assertFalse((self.target / '.agents/gest-git-install.json').exists())

    def test_bundled_helper_requires_remote_commit_and_uses_exact_commit(self):
        helper = self.source / '.agents/skills/gest_git_installer/scripts/install_gest_git_package.sh'
        env = dict(os.environ, AGENT_GEST_GIT_SKILLS_REPO=str(self.source))
        env.pop('AGENT_GEST_GIT_SKILLS_SOURCE', None)
        env.pop('AGENT_GEST_GIT_SKILLS_COMMIT', None)
        missing = subprocess.run(['bash', str(helper), str(self.target)], env=env, capture_output=True, text=True)
        self.assertEqual(missing.returncode, 64)
        self.assertIn('AGENT_GEST_GIT_SKILLS_COMMIT', missing.stderr)
        env['AGENT_GEST_GIT_SKILLS_COMMIT'] = self.commit
        installed = subprocess.run(['bash', str(helper), str(self.target)], env=env, capture_output=True, text=True)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertEqual(self.provenance()['source_revision'], self.commit)
        self.assertEqual(self.provenance()['source_requested_commit'], self.commit)

    def test_sync_hooks_merges(self):
        self.run_install()
        codex = self.target / '.codex/hooks.json'
        value = json.loads(codex.read_text())
        value['another'] = 'keep'
        codex.write_text(json.dumps(value))
        run = subprocess.run(['bash', str(self.source / 'scripts/sync_g_skills.sh'),
                              '--hooks', str(self.target)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(codex.read_text())['another'], 'keep')


if __name__ == '__main__':
    unittest.main()
