#!/usr/bin/env node
// Explicit, opt-in installation only. Does not touch hooks, approvals or shell startup files.
import { readFile, lstat, readdir, mkdir, open, rename, unlink, realpath, link } from 'node:fs/promises';
import { dirname, join, resolve, relative } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { createHash, randomUUID } from 'node:crypto';
import { execFileSync } from 'node:child_process';

const hash = data => createHash('sha256').update(data).digest('hex');
function publicRemote(raw) {
  try {
    const url = new URL(raw);
    url.username = ''; url.password = ''; url.search = ''; url.hash = '';
    return url.toString().replace(/\/$/, '');
  } catch {
    const scp = /^[^@]+@([^:]+):(.+)$/.exec(raw || '');
    return scp ? `ssh://${scp[1]}/${scp[2]}` : null;
  }
}
async function stat(path) { try { return await lstat(path); } catch (e) { if (e.code !== 'ENOENT') throw e; return null; } }
async function safePath(path) {
  let current = resolve(path);
  while (true) {
    const info = await stat(current);
    if (info?.isSymbolicLink()) throw new Error(`Refusing symlinked installation path: ${current}; use copied native skills`);
    if (current !== path && info && !info.isDirectory()) throw new Error(`Parent is not a directory: ${current}`);
    const parent = dirname(current); if (parent === current) break; current = parent;
  }
}
async function filesUnder(root, prefix = '') {
  const result = [];
  for (const name of await readdir(join(root, prefix))) {
    const rel = join(prefix, name), info = await lstat(join(root, rel));
    if (info.isSymbolicLink()) throw new Error('Source skill must contain only regular files/directories');
    if (info.isDirectory()) result.push(...await filesUnder(root, rel));
    else if (info.isFile()) result.push(rel);
    else throw new Error('Unsupported skill file');
  }
  return result.sort();
}
async function fingerprint(path) {
  await safePath(path);
  const info = await stat(path);
  if (!info) return null;
  if (!info.isFile()) throw new Error(`Expected a regular installation file: ${path}`);
  return `${info.dev}:${info.ino}:${info.mode}:${hash(await readFile(path))}`;
}
async function unchanged(path, expected) {
  if (await fingerprint(path) !== expected) throw new Error(`File changed during installation; preserve/reconcile before retry: ${path}`);
}
async function atomic(path, data, mode, expected) {
  await mkdir(dirname(path), { recursive: true, mode: 0o755 });
  const temp = `${path}.${randomUUID()}.tmp`;
  const handle = await open(temp, 'wx', mode);
  try {
    await handle.writeFile(data); await handle.sync(); await handle.close();
    await unchanged(path, expected);
    if (expected === null) await link(temp, path);
    else await rename(temp, path);
  } finally { await handle.close().catch(() => {}); await unlink(temp).catch(() => {}); }
}

let installationLock, installationLockPath;
try {
  if (Number(process.versions.node.split('.')[0]) < 22) throw new Error('Lanes requires Node.js 22 or newer; no npm dependencies. Gest/git/just/uv are optional and not needed by Lanes.');
  const args = process.argv.slice(2);
  let home = homedir(), cliOnly = false, dryRun = false, explicitHome = false;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--home' && args[i + 1]) { home = resolve(args[++i]); explicitHome = true; }
    else if (args[i] === '--cli-only') cliOnly = true;
    else if (args[i] === '--dry-run') dryRun = true;
    else throw new Error('Usage: node install.mjs [--home DIR] [--cli-only] [--dry-run]');
  }
  // macOS temporary directories can pass through /var -> /private/var.
  // Resolve the explicitly selected base, then reject links in managed paths.
  home = await realpath(home);
  const source = resolve(dirname(fileURLToPath(import.meta.url)), '..');
  const manifest = join(home, '.local/share/lanes/install.json');
  const bin = join(home, '.local/bin/lanes');
  if (!dryRun) {
    installationLockPath = join(home, '.local/share/lanes/install.lock');
    await safePath(installationLockPath);
    await mkdir(dirname(installationLockPath), { recursive: true, mode: 0o755 });
    try { installationLock = await open(installationLockPath, 'wx', 0o600); }
    catch (e) { if (e.code === 'EEXIST') throw new Error('Lanes installation already running or interrupted; reconcile install.lock explicitly'); throw e; }
  }
  const roots = cliOnly ? [] : [join(explicitHome ? join(home, '.codex') : (process.env.CODEX_HOME || join(home, '.codex')), 'skills/lanes'), join(home, '.claude/skills/lanes')];
  const launcher = '#!/usr/bin/env node\nconst { join } = require("node:path");\nconst { pathToFileURL } = require("node:url");\nimport(pathToFileURL(join(__dirname, "../share/lanes/lanes.mjs")).href).then(({ main }) => main()).catch(() => { console.error("Lanes runtime unavailable; reinstall the client"); process.exitCode = 1; });\n';
  const planned = new Map([
    [bin, { data: Buffer.from(launcher), mode: 0o755 }],
    [join(home, '.local/share/lanes/lanes.mjs'), { data: await readFile(join(source, 'scripts/lanes.mjs')), mode: 0o644 }],
  ]);
  const sourceFiles = await filesUnder(source);
  const bundle = {};
  for (const rel of sourceFiles) {
    const data = await readFile(join(source, rel)); bundle[rel] = hash(data);
    for (const root of roots) planned.set(join(root, rel), { data, mode: rel.endsWith('.mjs') ? 0o755 : 0o644 });
  }
  await safePath(manifest);
  const expectedManifest = await fingerprint(manifest);
  let previous = {};
  if (await stat(manifest)) {
    try { previous = JSON.parse(await readFile(manifest, 'utf8')); }
    catch { throw new Error('Invalid previous installation manifest JSON; contents withheld'); }
    if (previous.version !== 1 || typeof previous.files !== 'object' || !previous.files) throw new Error('Invalid previous installation manifest');
  }
  const expectedFiles = new Map();
  for (const [path, { data }] of planned) {
    await safePath(path);
    const info = await stat(path);
    if (info && (!info.isFile() || (hash(await readFile(path)) !== hash(data) && hash(await readFile(path)) !== previous.files?.[path]))) throw new Error(`Existing file has user changes; preserve/reconcile before reinstall: ${path}`);
    expectedFiles.set(path, await fingerprint(path));
  }
  let revision = null, dirty = null, sourceRepository = null, sourceRevision = null;
  try {
    const repo = execFileSync('git', ['-C', source, 'rev-parse', '--show-toplevel'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
    execFileSync('git', ['-C', repo, 'ls-files', '--error-unmatch', join(relative(repo, source), 'SKILL.md')], { stdio: 'ignore' });
    sourceRevision = execFileSync('git', ['-C', repo, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
    dirty = Boolean(execFileSync('git', ['-C', repo, 'status', '--porcelain', '--', relative(repo, source)], { encoding: 'utf8' }).trim());
    try { sourceRepository = publicRemote(execFileSync('git', ['-C', repo, 'config', '--get', 'remote.origin.url'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()); } catch { /* No upstream identity. */ }
    if (/^(https|ssh):\/\/github\.com\/rahuldave\/agent_gest_git_skills(?:\.git)?$/i.test(sourceRepository || '')) revision = sourceRevision;
  } catch { /* Installed skill-only copies retain exact content hashes without claiming a Git revision. */ }
  const current = {
    version: 1, repository: 'https://github.com/rahuldave/agent_gest_git_skills', revision, sourceDirty: dirty,
    sourceRepository, sourceRevision,
    bundleSha256: hash(JSON.stringify(bundle)), installedAt: new Date().toISOString(),
    files: { ...previous.files, ...Object.fromEntries([...planned].map(([path, { data }]) => [path, hash(data)])) },
  };
  // These belong to the surrounding Gest package. Report availability without
  // making them prerequisites for this independent Lanes client.
  const packageTools = {};
  for (const check of ['git --version', 'gest --version', 'just --version', 'uv --version', 'node --version', 'rsync --version', 'gh --version', 'but --version', 'ast-grep --version', 'direnv version', 'cx --help']) {
    const [program, argument] = check.split(' ');
    try { execFileSync(program, [argument], { stdio: 'ignore', timeout: 2000 }); packageTools[program] = 'available'; }
    catch { packageTools[program] = 'unavailable (not required by Lanes)'; }
  }
  if (!dryRun) {
    await unchanged(manifest, expectedManifest);
    for (const path of planned.keys()) await unchanged(path, expectedFiles.get(path));
    for (const [path, { data, mode }] of planned) await atomic(path, data, mode, expectedFiles.get(path));
    await atomic(manifest, `${JSON.stringify(current, null, 2)}\n`, 0o644, expectedManifest);
  }
  console.log(JSON.stringify({ installed: !dryRun, dryRun, command: bin, skills: roots, manifest, revision, sourceRepository, sourceRevision, sourceDirty: dirty, bundleSha256: current.bundleSha256, prerequisites: { required: 'Node.js >=22', optionalPackageTools: packageTools }, pathInstruction: 'Ensure ~/.local/bin is on PATH. Restart agent sessions to discover the installed skill. No credentials or project bindings were installed.' }, null, 2));
} catch (e) { console.error(e.message); process.exitCode = 1; }
finally { if (installationLock) { await installationLock.close(); await unlink(installationLockPath); } }
