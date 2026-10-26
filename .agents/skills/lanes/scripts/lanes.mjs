#!/usr/bin/env node
// Standalone direct-cloud client. No package install, listener, queue or background process.
import { readFile, lstat, mkdir, open, rename, unlink, link, realpath } from 'node:fs/promises';
import { homedir } from 'node:os';
import { dirname, join, resolve, isAbsolute } from 'node:path';
import { pathToFileURL } from 'node:url';
import { randomUUID, createHash } from 'node:crypto';

const LIMIT = 65536;
const usage = 'Usage: lanes [--project DIR] --principal NAME doctor | workspace get | items list | todo|attention create|list|get|update|respond|resolve|withdraw|dismiss [ID] [--lane ID] [--key KEY]. JSON on stdin for writes. Setup: lanes bind | credential add [--replace].';
const id = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,120}$/.test(value);
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);

export function origin(value) {
  const url = new URL(value);
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname))) throw new Error('Cloud API requires HTTPS');
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/') throw new Error('Use a clean API origin');
  return url.origin;
}
function binding(value) {
  if (!object(value) || value.version !== 1 || !id(value.workspaceId) || !id(value.projectId) || !id(value.laneId)) throw new Error('Invalid version 1 project binding');
  const allowed = new Set(['version', 'apiUrl', 'workspaceId', 'projectId', 'laneId', 'sessionLabel']);
  if (Object.keys(value).some(key => !allowed.has(key))) throw new Error('Unknown project binding field; credentials do not belong in a public binding');
  if (value.sessionLabel !== undefined && (typeof value.sessionLabel !== 'string' || value.sessionLabel.length > 300)) throw new Error('Invalid session label');
  return { version: 1, apiUrl: origin(value.apiUrl), workspaceId: value.workspaceId, projectId: value.projectId, laneId: value.laneId, ...(value.sessionLabel === undefined ? {} : { sessionLabel: value.sessionLabel }) };
}
function parse(input) {
  if (Buffer.byteLength(input) > LIMIT) throw new Error('Payload exceeds 64 KiB');
  const result = parseJson(input || '{}');
  if (!object(result)) throw new Error('JSON object required');
  return result;
}
function parseJson(input) {
  try { return JSON.parse(input); }
  catch { throw new Error('Invalid JSON; input contents withheld'); }
}
async function exists(path) {
  try { return await lstat(path); } catch (e) { if (e.code !== 'ENOENT') throw e; return null; }
}
async function readJson(path, max = LIMIT) {
  const stat = await lstat(path);
  if (!stat.isFile() || stat.isSymbolicLink()) throw new Error('Expected a regular non-symlink file');
  if (stat.size > max) throw new Error('Configuration file too large');
  return parseJson(await readFile(path, 'utf8'));
}
async function findBinding(start) {
  let directory = await realpath(resolve(start));
  while (true) {
    const path = join(directory, '.lanes.json');
    if (await exists(path)) return { ...binding(await readJson(path)), path };
    if (await exists(join(directory, '.git'))) break;
    const parent = dirname(directory);
    if (parent === directory) break;
    directory = parent;
  }
  throw new Error('No .lanes.json in this project; register and bind the project explicitly');
}
function credentialsPath(env) {
  const path = env.LANES_CREDENTIALS_FILE || join(env.XDG_CONFIG_HOME || join(homedir(), '.config'), 'lanes', 'credentials.json');
  if (!isAbsolute(path)) throw new Error('Credentials path must be absolute');
  return path;
}
async function readCredentials(path) {
  const stat = await lstat(path);
  if (!stat.isFile() || stat.isSymbolicLink()) throw new Error('Credentials must be a regular non-symlink file');
  if ((stat.mode & 0o777) !== 0o600 || (process.getuid && stat.uid !== process.getuid())) throw new Error('Credentials must be owned by this user and mode 0600');
  const value = await readJson(path, 1024 * 1024);
  if (value.version !== 1 || !Array.isArray(value.grants)) throw new Error('Invalid credential store');
  return value;
}
function grant(value) {
  if (!object(value) || !id(value.workspaceId) || !id(value.projectId) || !id(value.principal) || typeof value.token !== 'string' || value.token.length < 16 || /[\r\n]/.test(value.token)) throw new Error('Invalid scoped credential grant');
  return { apiUrl: origin(value.apiUrl), workspaceId: value.workspaceId, projectId: value.projectId, principal: value.principal, token: value.token };
}
const sameGrant = (a, b) => a.apiUrl === b.apiUrl && a.workspaceId === b.workspaceId && a.projectId === b.projectId && a.principal === b.principal;
async function atomicWrite(path, data, mode, exclusive = false) {
  await mkdir(dirname(path), { recursive: true, mode: 0o700 });
  const temporary = `${path}.${randomUUID()}.tmp`;
  const handle = await open(temporary, 'wx', mode);
  try {
    await handle.writeFile(data); await handle.sync(); await handle.close();
    if (exclusive) {
      // Atomic exclusive creation; no partial final file after a setup crash.
      await link(temporary, path);
    } else await rename(temporary, path);
  } finally { await handle.close().catch(() => {}); await unlink(temporary).catch(() => {}); }
}

export class CloudClient {
  constructor(base, token, transport = fetch) {
    this.url = origin(base); this.token = token; this.transport = transport;
  }
  async request(method, path, body, key = randomUUID()) {
    const target = new URL(path, this.url);
    if (!path.startsWith('/v1/') || target.origin !== this.url || !target.pathname.startsWith('/v1/')) throw new Error('Invalid API path');
    const serialized = body === undefined ? undefined : JSON.stringify(body);
    let last = 'request failed';
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const response = await this.transport(target, {
          method, headers: { Authorization: `Bearer ${this.token}`, 'Content-Type': 'application/json', 'Idempotency-Key': key },
          body: serialized, signal: AbortSignal.timeout(8000), redirect: 'error',
        });
        const data = await response.json();
        if (!response.ok) {
          if (response.status < 500 && response.status !== 429) {
            const error = new Error(`API rejected command (HTTP ${response.status}): ${typeof data?.error === 'string' ? data.error : 'request_rejected'}`);
            error.confirmed = true; throw error;
          }
          last = `HTTP ${response.status}`;
        } else if (method !== 'GET' && data?.receipt?.durable !== true) last = 'missing durable receipt';
        else return data;
      } catch (e) {
        if (e.confirmed) throw e;
        // Transport errors may include headers/credentials. Emit only a generic failure.
        last = 'transport or response failure';
      }
      if (attempt < 2) await new Promise(accept => setTimeout(accept, 100 * (attempt + 1)));
    }
    throw new Error(`not confirmed: ${last}; reconcile by resource ID and command key ${key}`);
  }
  async listItems(laneId) {
    const items = [], seen = new Set();
    let cursor = null, total = 0, pages = 0;
    do {
      const query = new URLSearchParams({ limit: '200', laneId });
      if (cursor) query.set('cursor', cursor);
      const page = await this.request('GET', `/v1/items?${query}`);
      if (!Array.isArray(page.items) || !Number.isSafeInteger(page.total) || page.total < 0 || (page.nextCursor !== null && typeof page.nextCursor !== 'string')) throw new Error('Invalid pagination response');
      items.push(...page.items); total = page.total; cursor = page.nextCursor;
      if (cursor && (seen.has(cursor) || ++pages >= 100 || items.length > 10000)) throw new Error('Incomplete pagination; reconcile before proceeding');
      if (cursor) seen.add(cursor);
    } while (cursor);
    return { items, total, nextCursor: null };
  }
}

function argumentsFor(argv) {
  const args = [], flags = {};
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (['--project', '--principal', '--lane', '--key'].includes(arg)) {
      if (!argv[index + 1] || argv[index + 1].startsWith('--') || flags[arg]) throw new Error(usage);
      flags[arg] = argv[++index];
    } else if (arg === '--replace') flags[arg] = true;
    else if (arg.startsWith('-')) throw new Error(usage);
    else args.push(arg);
  }
  if (!args.length || args.length > 3) throw new Error(usage);
  return { args, flags };
}
export async function run(argv, { cwd = process.cwd(), env = process.env, input = '', transport = fetch } = {}) {
  const { args, flags } = argumentsFor(argv);
  const [resource, action, itemId] = args;
  const directory = resolve(cwd, flags['--project'] || '.');
  if (resource === 'bind' && !action) {
    const value = binding(parse(input));
    const path = join(directory, '.lanes.json');
    if (await exists(path)) {
      const old = binding(await readJson(path));
      if (JSON.stringify(old) !== JSON.stringify(value)) throw new Error('Project binding already exists; review changes explicitly');
    } else await atomicWrite(path, `${JSON.stringify(value, null, 2)}\n`, 0o644, true);
    return { bound: true, path, projectId: value.projectId };
  }
  if (resource === 'credential' && action === 'add' && !itemId) {
    const value = grant(parse(input)), path = credentialsPath(env);
    await mkdir(dirname(path), { recursive: true, mode: 0o700 });
    const lockPath = `${path}.setup.lock`;
    let lock;
    try { lock = await open(lockPath, 'wx', 0o600); }
    catch (e) { if (e.code === 'EEXIST') throw new Error('Credential setup already running or interrupted; reconcile the setup lock explicitly'); throw e; }
    try {
      const stored = await exists(path) ? await readCredentials(path) : { version: 1, grants: [] };
      const matches = stored.grants.filter(g => sameGrant(g, value));
      if (matches.length > 1) throw new Error('Ambiguous credential grants; reconcile store');
      if (matches.length && matches[0].token !== value.token && !flags['--replace']) throw new Error('Credential already exists; use --replace for deliberate rotation');
      stored.grants = [...stored.grants.filter(g => !sameGrant(g, value)), value];
      await atomicWrite(path, `${JSON.stringify(stored, null, 2)}\n`, 0o600, !(await exists(path)));
    } finally { await lock.close(); await unlink(lockPath); }
    return { configured: true, apiUrl: value.apiUrl, workspaceId: value.workspaceId, projectId: value.projectId, principal: value.principal };
  }
  if (flags['--replace']) throw new Error(usage);
  const principal = flags['--principal'] || env.LANES_PRINCIPAL;
  if (!id(principal)) throw new Error('Choose --principal codex|claude (or the configured agent principal) explicitly');
  const project = await findBinding(directory);
  const stored = await readCredentials(credentialsPath(env));
  const identity = { ...project, principal };
  const matches = stored.grants.map(grant).filter(g => sameGrant(g, identity));
  if (matches.length > 1) throw new Error('Ambiguous credential grants; reconcile store');
  if (matches.length !== 1) throw new Error('No matching scoped credential for this API/workspace/project/principal; publication not confirmed');
  const safe = { apiUrl: project.apiUrl, workspaceId: project.workspaceId, projectId: project.projectId, laneId: project.laneId, principal };
  if (resource === 'doctor' && !action) return { configured: true, ...safe, binding: project.path };
  const lane = flags['--lane'] || project.laneId;
  if (!id(lane) || (itemId && !id(itemId))) throw new Error('Invalid resource identity');
  const enc = encodeURIComponent;
  let path, method = 'GET';
  if (resource === 'workspace' && action === 'get' && !itemId) path = '/v1/workspace';
  else if (resource === 'items' && action === 'list' && !itemId) path = 'items';
  else if (['todo', 'attention'].includes(resource)) {
    path = `/v1/lanes/${enc(lane)}/${resource === 'todo' ? 'todos' : 'attention'}`;
    if (itemId) path += `/${enc(itemId)}`;
    if (action === 'create' && !itemId) method = 'POST';
    else if ((action === 'list' && !itemId) || (action === 'get' && itemId)) method = 'GET';
    else if (action === 'update' && itemId) method = 'PATCH';
    else if (resource === 'attention' && ['respond', 'resolve', 'withdraw', 'dismiss'].includes(action) && itemId) { method = 'POST'; path += `/${action}`; }
    else throw new Error(usage);
  } else throw new Error(usage);
  let body;
  if (method !== 'GET') {
    body = parse(input);
    if (action === 'create') {
      body.itemId ??= randomUUID();
      if (resource === 'attention') {
        if (!object(body.source)) throw new Error('Attention needs the actual source provider, sessionId and sessionLabel');
        body.source.projectId ??= project.projectId;
        if (body.source.projectId !== project.projectId) throw new Error('Attention source project differs from binding');
      }
    }
  }
  const key = flags['--key'] || env.LANES_COMMAND_KEY || randomUUID();
  if (key.length > 200 || /[\r\n]/.test(key)) throw new Error('Invalid command key');
  const client = new CloudClient(project.apiUrl, matches[0].token, transport);
  try {
    if (path === 'items') return await client.listItems(lane);
    const result = await client.request(method, path, body, key);
    return method === 'GET' ? result : { ...result, client: { commandKey: key, resourceId: body.itemId || itemId, ...safe, laneId: lane } };
  } catch (e) {
    e.resourceId = body?.itemId || itemId; e.commandKey = key; throw e;
  }
}

export async function main(argv = process.argv.slice(2)) {
  try {
    if (Number(process.versions.node.split('.')[0]) < 22) throw new Error('Lanes requires Node.js 22 or newer');
    if (argv.some(a => a === '--help' || a === '-h')) { console.log(usage); }
    else if (argv[0] === '--version') {
      const sha256 = createHash('sha256').update(await readFile(new URL(import.meta.url))).digest('hex');
      console.log(JSON.stringify({ version: '0.1.0', sha256 }));
    } else {
      const chunks = []; let size = 0;
      // Read stdin only for mutations; interactive reads must not wait for EOF.
      const { args: [resource, action] } = argumentsFor(argv);
      const needsInput = (resource === 'bind' && !action) || (resource === 'credential' && action === 'add') || (['todo', 'attention'].includes(resource) && ['create', 'update', 'respond', 'resolve', 'withdraw', 'dismiss'].includes(action));
      if (needsInput) {
        for await (const chunk of process.stdin) {
          const bytes = Buffer.from(chunk); size += bytes.length; chunks.push(bytes);
          if (size > LIMIT) throw new Error('Payload exceeds 64 KiB');
        }
      }
      console.log(JSON.stringify(await run(argv, { input: Buffer.concat(chunks).toString('utf8') }), null, 2));
    }
  } catch (e) {
    console.error(JSON.stringify({ error: e.code === 'ENOENT' ? 'Lanes configuration missing; publication not confirmed' : e.message, resourceId: e.resourceId, commandKey: e.commandKey }));
    process.exitCode = 1;
  }
}
if (process.argv[1] && import.meta.url === pathToFileURL(await realpath(resolve(process.argv[1]))).href) await main();
