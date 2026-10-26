import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, mkdir, readFile, writeFile, chmod, symlink, rm, cp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawn, execFileSync } from 'node:child_process';
import { createServer } from 'node:http';
import { CloudClient, run } from '../.agents/skills/lanes/scripts/lanes.mjs';

const source = resolve('.agents/skills/lanes');
async function scratch(fn) {
  const root = await mkdtemp(join(tmpdir(), 'lanes-portable-'));
  try { await fn(root); } finally { await rm(root, { recursive: true, force: true }); }
}
async function fixture(root, apiUrl = 'https://lanes.example') {
  const project = join(root, 'project');
  await mkdir(join(project, 'nested'), { recursive: true });
  const binding = { version: 1, apiUrl, workspaceId: 'ws', projectId: 'proj', laneId: 'lane' };
  await writeFile(join(project, '.lanes.json'), JSON.stringify(binding));
  const credentials = join(root, 'credentials.json');
  await writeFile(credentials, JSON.stringify({ version: 1, grants: [
    { ...binding, principal: 'codex', token: 'codex-private-token' },
    { ...binding, principal: 'claude', token: 'claude-private-token' },
  ] }), { mode: 0o600 });
  return { project, binding, credentials, env: { LANES_CREDENTIALS_FILE: credentials } };
}
async function command(file, args, { cwd, env = {}, input = '' } = {}) {
  return new Promise((accept, reject) => {
    const child = spawn(process.execPath, [file, ...args], { cwd, env: { ...process.env, ...env }, stdio: 'pipe' });
    let stdout = '', stderr = '';
    child.stdout.on('data', b => stdout += b);
    child.stderr.on('data', b => stderr += b);
    child.on('error', reject);
    child.on('close', code => accept({ code, stdout, stderr }));
    child.stdin.end(input);
  });
}

test('uncertain writes retry the identical command and require a durable receipt', async () => {
  const seen = [];
  const client = new CloudClient('https://lanes.example', 'secret', async (url, init) => {
    seen.push({ url: String(url), ...init });
    if (seen.length === 1) throw new Error('connection lost');
    if (seen.length === 2) return Response.json({ resource: {} });
    return Response.json({ receipt: { durable: true }, resource: { itemId: 'stable' } });
  });
  await client.request('POST', '/v1/lanes/lane/todos', { itemId: 'stable' }, 'same-key');
  assert.equal(seen.length, 3);
  assert.equal(new Set(seen.map(r => r.body)).size, 1);
  assert.deepEqual(seen.map(r => r.headers['Idempotency-Key']), Array(3).fill('same-key'));
  assert.ok(seen.every(r => r.redirect === 'error'));
  await assert.rejects(new CloudClient('https://lanes.example', 'secret', async () => Response.json({})).request('POST', '/v1/lanes', {}, 'recover-key'), /not confirmed.*recover-key/);
});

test('confirmed API rejection is not retried; pagination is complete and bounded', async () => {
  let calls = 0;
  const reject = new CloudClient('https://lanes.example', 'secret', async () => {
    calls++;
    return Response.json({ error: 'revision_conflict' }, { status: 409 });
  });
  await assert.rejects(reject.request('PATCH', '/v1/lanes/lane/todos/id', {}, 'key'), /HTTP 409/);
  assert.equal(calls, 1);
  const paths = [];
  const pages = new CloudClient('https://lanes.example', 'secret', async url => {
    paths.push(String(url));
    return Response.json(paths.length === 1 ? { items: [{ itemId: 'a' }], total: 2, nextCursor: 'a /?' } : { items: [{ itemId: 'b' }], total: 2, nextCursor: null });
  });
  assert.equal((await pages.listItems('lane')).items.length, 2);
  assert.equal(new URL(paths[1]).searchParams.get('cursor'), 'a /?');
  const loop = new CloudClient('https://lanes.example', 'secret', async () => Response.json({ items: [], total: 3, nextCursor: 'again' }));
  await assert.rejects(loop.listItems('lane'), /pagination/);
});

test('binding lookup works in nested paths, pins credentials to origin/workspace/project/principal', async () => scratch(async root => {
  const f = await fixture(root);
  const options = { cwd: join(f.project, 'nested'), env: f.env };
  const doctor = await run(['--principal', 'codex', 'doctor'], options);
  assert.equal(doctor.configured, true);
  assert.equal(doctor.projectId, 'proj');
  assert.ok(!JSON.stringify(doctor).includes('private-token'));
  await assert.rejects(run(['doctor'], options), /principal/);
  let sent;
  const result = await run(['--principal', 'claude', 'todo', 'create', '--key', 'stable-key'], {
    ...options, input: '{"itemId":"task","title":"Keep me"}', transport: async (url, init) => {
      sent = { url: String(url), ...init };
      return Response.json({ receipt: { durable: true }, resource: { itemId: 'task', state: 'draft' } });
    },
  });
  assert.equal(sent.headers.Authorization, 'Bearer claude-private-token');
  assert.equal(result.client.commandKey, 'stable-key');
  for (const delta of [{ apiUrl: 'https://evil.example' }, { projectId: 'elsewhere' }, { workspaceId: 'elsewhere' }]) {
    await writeFile(join(f.project, '.lanes.json'), JSON.stringify({ ...f.binding, ...delta }));
    await assert.rejects(run(['--principal', 'codex', 'items', 'list'], { ...options, transport: () => { throw new Error('must not send'); } }), /No matching scoped credential/);
  }
}));

test('unsafe credential files, ambiguous grants and git-boundary borrowing fail before sending', async () => scratch(async root => {
  const f = await fixture(root);
  const options = { cwd: f.project, env: f.env };
  await chmod(f.credentials, 0o644);
  await assert.rejects(run(['--principal', 'codex', 'doctor'], options), /0600/);
  await chmod(f.credentials, 0o600);
  await symlink(f.credentials, join(root, 'linked.json'));
  await assert.rejects(run(['--principal', 'codex', 'doctor'], { ...options, env: { LANES_CREDENTIALS_FILE: join(root, 'linked.json') } }), /regular.*file/);
  const stored = JSON.parse(await readFile(f.credentials));
  stored.grants.push(stored.grants[0]);
  await writeFile(f.credentials, JSON.stringify(stored));
  await assert.rejects(run(['--principal', 'codex', 'doctor'], options), /ambiguous/i);
  await mkdir(join(f.project, 'nested', '.git'));
  await assert.rejects(run(['--principal', 'codex', 'doctor'], { ...options, cwd: join(f.project, 'nested') }), /No .lanes.json/);
  const foreign = join(root, 'unbound-repo');
  await mkdir(join(foreign, '.git'), { recursive: true }); await mkdir(join(foreign, 'subdir'));
  await symlink(join(foreign, 'subdir'), join(f.project, 'linked-subdir'));
  await assert.rejects(run(['--project', join(f.project, 'linked-subdir'), '--principal', 'codex', 'doctor'], options), /No .lanes.json/);
}));

test('attention source is real caller data; reading is GET and neither read nor reply resolves', async () => scratch(async root => {
  const f = await fixture(root);
  const sent = [];
  const options = { cwd: f.project, env: f.env, transport: async (url, init) => {
    sent.push({ url: String(url), ...init });
    return Response.json(init.method === 'GET' ? { resource: { state: 'responded' } } : { resource: { itemId: 'request' }, receipt: { durable: true } });
  } };
  const body = { itemId: 'request', title: 'Review', kind: 'review', actionNeeded: 'Please review this change.', source: { provider: 'codex', sessionId: 'actual-id', sessionLabel: 'Actual conversation' } };
  await run(['--principal', 'codex', 'attention', 'create'], { ...options, input: JSON.stringify(body) });
  assert.equal(JSON.parse(sent[0].body).source.projectId, 'proj');
  await run(['--principal', 'codex', 'attention', 'get', 'request'], options);
  await run(['--principal', 'codex', 'attention', 'respond', 'request'], { ...options, input: '{"expectedRevision":1,"text":"Yes"}' });
  assert.deepEqual(sent.map(r => r.method), ['POST', 'GET', 'POST']);
  assert.ok(sent[2].url.endsWith('/respond'));
  assert.ok(sent.every(r => !r.url.includes('/resolve')));
  await assert.rejects(run(['--principal', 'codex', 'attention', 'oops', 'request'], options), /Usage/);
  await assert.rejects(run(['--principal', 'codex', 'todo', 'create'], { ...options, input: 'x'.repeat(65537) }), /64 KiB/);
}));

test('bind and credential provisioning are explicit, private and repeat-safe', async () => scratch(async root => {
  const project = join(root, 'project'); await mkdir(project);
  const env = { LANES_CREDENTIALS_FILE: join(root, 'auth.json') };
  const binding = { version: 1, apiUrl: 'https://lanes.example', workspaceId: 'ws', projectId: 'proj', laneId: 'lane' };
  await assert.rejects(run(['bind'], { cwd: project, env, input: JSON.stringify({ ...binding, token: 'must-never-be-public' }) }), /Unknown project binding/);
  await assert.rejects(readFile(join(project, '.lanes.json')), /ENOENT/);
  await run(['bind'], { cwd: project, env, input: JSON.stringify(binding) });
  await run(['bind'], { cwd: project, env, input: JSON.stringify(binding) });
  await assert.rejects(run(['bind'], { cwd: project, env, input: JSON.stringify({ ...binding, projectId: 'new' }) }), /already exists/);
  const grant = { ...binding, principal: 'codex', token: 'protected-codex-token' };
  await run(['credential', 'add'], { cwd: root, env, input: JSON.stringify(grant) });
  assert.equal((await run(['--project', project, '--principal', 'codex', 'doctor'], { cwd: root, env })).configured, true);
  const changed = JSON.stringify({ ...grant, token: 'different-scoped-token' });
  await assert.rejects(run(['credential', 'add'], { cwd: root, env, input: changed }), /already exists/);
  await run(['credential', 'add', '--replace'], { cwd: root, env, input: changed });
}));

test('GET resource IDs and flag values named update never wait for stdin EOF', async () => scratch(async root => {
  const f = await fixture(root);
  const server = createServer((_req, res) => {
    res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ resource: { itemId: 'update', state: 'draft' } }));
  });
  await new Promise(accept => server.listen(0, '127.0.0.1', accept));
  try {
    const origin = `http://127.0.0.1:${server.address().port}`;
    await writeFile(join(f.project, '.lanes.json'), JSON.stringify({ ...f.binding, apiUrl: origin }));
    const stored = JSON.parse(await readFile(f.credentials));
    for (const grant of stored.grants) grant.apiUrl = origin;
    await writeFile(f.credentials, JSON.stringify(stored));
    for (const args of [['todo', 'get', 'update'], ['todo', 'get', 'id', '--lane', 'update']]) {
      const result = await new Promise((accept, reject) => {
        const child = spawn(process.execPath, [join(source, 'scripts/lanes.mjs'), '--principal', 'codex', ...args], { cwd: f.project, env: { ...process.env, ...f.env }, stdio: 'pipe' });
        let stdout = '', stderr = '';
        child.stdout.on('data', b => stdout += b); child.stderr.on('data', b => stderr += b);
        const timer = setTimeout(() => { child.kill(); reject(new Error('GET waited for stdin EOF')); }, 3000);
        child.on('error', reject);
        child.on('close', code => { clearTimeout(timer); accept({ code, stdout, stderr }); });
        // Deliberately leave stdin open. A read must finish without consuming it.
      });
      assert.equal(result.code, 0, result.stderr);
      assert.equal(JSON.parse(result.stdout).resource.itemId, 'update');
    }
  } finally { await new Promise(accept => server.close(accept)); }
}));

test('installed CLI and both native skills work outside source; reinstall preserves user edits and unrelated files', async () => scratch(async root => {
  const home = join(root, 'home'); await mkdir(home);
  await mkdir(join(home, '.claude'), { recursive: true });
  const settings = '{"permissions":{"defaultMode":"default"},"userSetting":true}';
  await writeFile(join(home, '.claude/settings.json'), settings);
  const installer = join(source, 'scripts/install.mjs');
  const preview = await command(installer, ['--home', home, '--dry-run']);
  assert.equal(preview.code, 0, preview.stderr);
  await assert.rejects(readFile(join(home, '.local/bin/lanes')), /ENOENT/);
  const install = await command(installer, ['--home', home]);
  assert.equal(install.code, 0, install.stderr);
  assert.equal(await readFile(join(home, '.claude/settings.json'), 'utf8'), settings);
  for (const provider of ['.codex', '.claude']) {
    const skill = await readFile(join(home, provider, 'skills/lanes/SKILL.md'), 'utf8');
    assert.match(skill, /name: lanes/);
  }
  const bin = join(home, '.local/bin/lanes');
  const f = await fixture(root, 'http://127.0.0.1');
  const server = createServer((req, res) => {
    assert.equal(req.headers.authorization, 'Bearer codex-private-token');
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ items: [{ itemId: 'outside' }], total: 1, nextCursor: null }));
  });
  await new Promise(accept => server.listen(0, '127.0.0.1', accept));
  try {
    const origin = `http://127.0.0.1:${server.address().port}`;
    const binding = { ...f.binding, apiUrl: origin };
    await writeFile(join(f.project, '.lanes.json'), JSON.stringify(binding));
    const stored = JSON.parse(await readFile(f.credentials));
    for (const grant of stored.grants) grant.apiUrl = origin;
    await writeFile(f.credentials, JSON.stringify(stored));
    const result = await command(bin, ['--principal', 'codex', 'items', 'list'], { cwd: join(f.project, 'nested'), env: f.env });
    assert.equal(result.code, 0, result.stderr);
    assert.equal(JSON.parse(result.stdout).items[0].itemId, 'outside');
  } finally { await new Promise(accept => server.close(accept)); }
  assert.equal((await command(installer, ['--home', home])).code, 0);
  await writeFile(bin, 'user owned command');
  const conflict = await command(installer, ['--home', home]);
  assert.notEqual(conflict.code, 0);
  assert.equal(await readFile(bin, 'utf8'), 'user owned command');
}));

test('symlinked native skill roots fail preflight without writing a CLI', async () => scratch(async root => {
  const home = join(root, 'home'), other = join(root, 'other');
  await mkdir(join(home, '.claude'), { recursive: true }); await mkdir(other);
  await symlink(other, join(home, '.claude/skills'));
  const result = await command(join(source, 'scripts/install.mjs'), ['--home', home]);
  assert.notEqual(result.code, 0);
  assert.match(result.stderr, /symlinked/);
  await assert.rejects(readFile(join(home, '.local/bin/lanes')), /ENOENT/);
}));

test('malformed credential stdin, saved credentials and install manifests never echo secret input', async () => scratch(async root => {
  const sentinel = 'REVIEW_SECRET_SENTINEL_DO_NOT_PRINT';
  const f = await fixture(root);
  const cli = join(source, 'scripts/lanes.mjs');
  const input = await command(cli, ['credential', 'add'], { cwd: root, env: f.env, input: sentinel });
  assert.notEqual(input.code, 0);
  assert.match(input.stderr, /Invalid JSON/);
  assert.ok(!(input.stderr + input.stdout).includes('REVIEW_SECRET'));
  await writeFile(f.credentials, sentinel);
  const stored = await command(cli, ['--principal', 'codex', 'doctor'], { cwd: f.project, env: f.env });
  assert.notEqual(stored.code, 0);
  assert.match(stored.stderr, /Invalid JSON/);
  assert.ok(!(stored.stderr + stored.stdout).includes('REVIEW_SECRET'));
  const home = join(root, 'home');
  await mkdir(join(home, '.local/share/lanes'), { recursive: true });
  await writeFile(join(home, '.local/share/lanes/install.json'), sentinel);
  const manifest = await command(join(source, 'scripts/install.mjs'), ['--home', home]);
  assert.notEqual(manifest.code, 0);
  assert.match(manifest.stderr, /contents withheld/);
  assert.ok(!(manifest.stderr + manifest.stdout).includes('REVIEW_SECRET'));
}));

test('installer preserves a file created after preflight and serializes concurrent installs', async () => scratch(async root => {
  const home = join(root, 'home'), fakebin = join(root, 'fakebin');
  await mkdir(home); await mkdir(fakebin);
  const fakeGit = `#!/usr/bin/env node\nif (process.argv[2] === '--version') { const fs = require('node:fs'), path = require('node:path'); if (process.env.LANES_RACE_TARGET) { fs.mkdirSync(path.dirname(process.env.LANES_RACE_TARGET), {recursive:true}); fs.writeFileSync(process.env.LANES_RACE_TARGET, 'concurrent user command'); } if (process.env.LANES_LOCK_MARKER) { fs.writeFileSync(process.env.LANES_LOCK_MARKER, 'ready'); setTimeout(() => process.exit(1), 800); } else process.exit(1); } else process.exit(1);\n`;
  await writeFile(join(fakebin, 'git'), fakeGit, { mode: 0o755 });
  const installer = join(source, 'scripts/install.mjs');
  const bin = join(home, '.local/bin/lanes');
  const env = { PATH: `${fakebin}:${process.env.PATH}`, LANES_RACE_TARGET: bin };
  const raced = await command(installer, ['--home', home], { env });
  assert.notEqual(raced.code, 0);
  assert.match(raced.stderr, /changed during installation/);
  assert.equal(await readFile(bin, 'utf8'), 'concurrent user command');
  await rm(bin);
  const marker = join(root, 'marker');
  const first = command(installer, ['--home', home], { env: { PATH: env.PATH, LANES_LOCK_MARKER: marker } });
  for (let i = 0; i < 100; i++) {
    try { await readFile(marker); break; } catch { await new Promise(accept => setTimeout(accept, 20)); }
  }
  assert.equal(await readFile(marker, 'utf8'), 'ready');
  const second = await command(installer, ['--home', home], { env: { PATH: env.PATH } });
  assert.notEqual(second.code, 0);
  assert.match(second.stderr, /installation already running/);
  assert.equal((await first).code, 0);
}));

test('skill copied into another Git project never claims that HEAD as its upstream revision', async () => scratch(async root => {
  const repo = join(root, 'another-project'), home = join(root, 'home');
  await mkdir(repo); await mkdir(home);
  const copied = join(repo, '.agents/skills/lanes');
  await cp(source, copied, { recursive: true });
  const git = (...args) => execFileSync('git', ['-C', repo, ...args], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
  git('init'); git('add', '.');
  git('-c', 'user.name=Lanes fixture', '-c', 'user.email=lanes@example.invalid', 'commit', '-m', 'Isolated copied skill');
  git('remote', 'add', 'origin', 'https://example.invalid/unrelated-project.git');
  const result = await command(join(copied, 'scripts/install.mjs'), ['--home', home]);
  assert.equal(result.code, 0, result.stderr);
  const manifest = JSON.parse(await readFile(join(home, '.local/share/lanes/install.json')));
  assert.equal(manifest.revision, null);
  assert.equal(manifest.sourceRevision, git('rev-parse', 'HEAD'));
  assert.equal(manifest.sourceRepository, 'https://example.invalid/unrelated-project.git');
  assert.equal(manifest.sourceDirty, false);
  assert.ok(manifest.bundleSha256);
  git('remote', 'set-url', 'origin', 'https://user:REVIEW_SECRET_SENTINEL@example.invalid/unrelated-project.git?token=REVIEW_SECRET_SENTINEL');
  const rerun = await command(join(copied, 'scripts/install.mjs'), ['--home', home]);
  assert.equal(rerun.code, 0, rerun.stderr);
  assert.ok(!(rerun.stdout + rerun.stderr + await readFile(join(home, '.local/share/lanes/install.json'), 'utf8')).includes('REVIEW_SECRET'));
}));
