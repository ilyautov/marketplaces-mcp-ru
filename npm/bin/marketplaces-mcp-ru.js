#!/usr/bin/env node
'use strict';
/*
 * npx launcher for marketplaces-mcp-ru (the Python package on PyPI).
 *
 * The MCP server itself is Python. This shim exists so that the install line
 * every MCP client documents — `npx -y marketplaces-mcp-ru` — works without the
 * user knowing anything about Python:
 *
 *   1. find `uv` (PATH, ~/.local/bin, ~/.cargo/bin, our own cache);
 *   2. if missing, download the official uv release for this OS/arch from
 *      GitHub, verify its sha256, unpack into ~/.cache/marketplaces-mcp-ru;
 *   3. run `uv tool run --from marketplaces-mcp-ru==<version> marketplaces-mcp-ru`
 *      — uv installs the package and a Python interpreter on first run;
 *   4. fallback without uv: `python3 -m pip install --target` into the cache.
 *
 * Everything this shim prints goes to stderr — stdout is the MCP transport.
 */
const { spawn, spawnSync } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const https = require('https');
const os = require('os');
const path = require('path');

const pkg = require('../package.json');
const PY_NAME = 'marketplaces-mcp-ru';
const VERSION = process.env.MARKETPLACES_MCP_RU_VERSION || pkg.version;
const PY_SPEC = VERSION === 'latest' ? PY_NAME : `${PY_NAME}==${VERSION}`;
const UV_VERSION = process.env.MARKETPLACES_MCP_RU_UV_VERSION || '0.12.10';
const HOME = process.env.MARKETPLACES_MCP_RU_HOME
  || path.join(os.homedir(), '.cache', 'marketplaces-mcp-ru');
const WIN = process.platform === 'win32';
const EXE = WIN ? '.exe' : '';

const log = (msg) => process.stderr.write(`[${PY_NAME}] ${msg}\n`);

// ---------------------------------------------------------------- uv lookup
function works(bin) {
  try {
    const r = spawnSync(bin, ['--version'], { stdio: 'ignore', timeout: 15000 });
    return r.status === 0;
  } catch (_) {
    return false;
  }
}

function findUv() {
  const home = os.homedir();
  const candidates = [
    path.join(HOME, 'uv', `uv${EXE}`),
    path.join(home, '.local', 'bin', `uv${EXE}`),
    path.join(home, '.cargo', 'bin', `uv${EXE}`),
  ];
  for (const dir of (process.env.PATH || '').split(path.delimiter)) {
    if (dir) candidates.push(path.join(dir, `uv${EXE}`));
  }
  for (const c of candidates) {
    if (fs.existsSync(c) && works(c)) return c;
  }
  return null;
}

// -------------------------------------------------------------- uv download
function uvTarget() {
  const arch = { x64: 'x86_64', arm64: 'aarch64', ia32: 'i686' }[process.arch];
  if (!arch) return null;
  if (process.platform === 'darwin') return `${arch}-apple-darwin`;
  if (process.platform === 'win32') return `${arch}-pc-windows-msvc`;
  if (process.platform === 'linux') {
    const musl = fs.existsSync('/etc/alpine-release');
    return `${arch}-unknown-linux-${musl ? 'musl' : 'gnu'}`;
  }
  return null;
}

function download(url, dest, redirects = 0) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { 'User-Agent': `${PY_NAME}-npm/${pkg.version}` } }, (res) => {
      if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location) {
        res.resume();
        if (redirects > 5) return reject(new Error('too many redirects'));
        return resolve(download(res.headers.location, dest, redirects + 1));
      }
      if (res.statusCode !== 200) {
        res.resume();
        return reject(new Error(`HTTP ${res.statusCode} for ${url}`));
      }
      const out = fs.createWriteStream(dest);
      res.pipe(out);
      out.on('finish', () => out.close(resolve));
      out.on('error', reject);
    }).on('error', reject);
  });
}

function sha256(file) {
  const h = crypto.createHash('sha256');
  h.update(fs.readFileSync(file));
  return h.digest('hex');
}

function findFile(dir, name) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      const hit = findFile(p, name);
      if (hit) return hit;
    } else if (entry.name === name) {
      return p;
    }
  }
  return null;
}

async function installUv() {
  if (process.env.MARKETPLACES_MCP_RU_NO_DOWNLOAD) return null;
  const target = uvTarget();
  if (!target) {
    log(`no uv build for ${process.platform}/${process.arch}`);
    return null;
  }
  const ext = WIN ? 'zip' : 'tar.gz';
  const asset = `uv-${target}.${ext}`;
  const base = `https://github.com/astral-sh/uv/releases/download/${UV_VERSION}`;
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'mmru-uv-'));
  const archive = path.join(tmp, asset);
  const sumFile = `${archive}.sha256`;
  try {
    log(`uv not found — downloading uv ${UV_VERSION} for ${target} (once, ~15 MB)`);
    await download(`${base}/${asset}`, archive);
    await download(`${base}/${asset}.sha256`, sumFile);
    const expected = fs.readFileSync(sumFile, 'utf8').trim().split(/\s+/)[0].toLowerCase();
    const actual = sha256(archive);
    if (expected !== actual) throw new Error(`sha256 mismatch for ${asset}`);

    const unpack = path.join(tmp, 'unpack');
    fs.mkdirSync(unpack);
    const tar = spawnSync('tar', ['-xf', archive, '-C', unpack], { stdio: ['ignore', 'ignore', 'inherit'] });
    if (tar.status !== 0) throw new Error('tar failed to unpack uv');

    const uvBin = findFile(unpack, `uv${EXE}`);
    if (!uvBin) throw new Error('uv binary not found in archive');
    const destDir = path.join(HOME, 'uv');
    fs.mkdirSync(destDir, { recursive: true });
    const dest = path.join(destDir, `uv${EXE}`);
    fs.copyFileSync(uvBin, dest);
    if (!WIN) fs.chmodSync(dest, 0o755);
    if (!works(dest)) throw new Error('downloaded uv does not run');
    log(`uv installed to ${dest}`);
    return dest;
  } catch (err) {
    log(`could not install uv: ${err.message}`);
    return null;
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

// --------------------------------------------------------- python fallback
function findPython() {
  for (const bin of ['python3', 'python', 'py']) {
    const r = spawnSync(bin, ['-c', 'import sys;print(sys.version_info>=(3,10))'],
      { encoding: 'utf8', timeout: 15000 });
    if (r.status === 0 && r.stdout.trim() === 'True') return bin;
  }
  return null;
}

// `pip install --target` into our cache instead of a venv: venv needs
// ensurepip, which some distro/Homebrew Pythons ship broken, while
// `python -m pip` on the base interpreter is almost always there.
function viaPip(args) {
  const py = findPython();
  if (!py) return null;
  const target = path.join(HOME, `site-${VERSION}`);
  const marker = path.join(target, 'core', 'combined.py');
  if (!fs.existsSync(marker)) {
    log(`uv unavailable — installing ${PY_SPEC} into ${target} with ${py}`);
    const base = ['-m', 'pip', 'install', '--quiet', '--disable-pip-version-check',
      '--upgrade', '--target', target, PY_SPEC];
    let r = spawnSync(py, base, { stdio: ['ignore', 'inherit', 'pipe'], encoding: 'utf8' });
    if (r.status !== 0 && /externally-managed/i.test(r.stderr || '')) {
      r = spawnSync(py, [...base, '--break-system-packages'], { stdio: ['ignore', 'inherit', 'inherit'] });
    } else if (r.status !== 0) {
      process.stderr.write(r.stderr || '');
    }
    if (r.status !== 0 || !fs.existsSync(marker)) {
      log(`pip install of ${PY_SPEC} failed (see above)`);
      return null;
    }
  }
  const env = { ...process.env, PYTHONPATH: target + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : '') };
  return { cmd: py, args: ['-m', 'core.combined', ...args], env };
}

// -------------------------------------------------------------------- main
function run({ cmd, args, env }) {
  const child = spawn(cmd, args, { stdio: 'inherit', windowsHide: true, env: env || process.env });
  for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) {
    process.on(sig, () => { try { child.kill(sig); } catch (_) { /* gone */ } });
  }
  child.on('error', (err) => {
    log(`failed to start ${cmd}: ${err.message}`);
    process.exit(1);
  });
  child.on('exit', (code, signal) => process.exit(code === null ? 1 : code, signal));
}

async function main() {
  const args = process.argv.slice(2);
  if (args[0] === '--wrapper-version') {
    process.stdout.write(`${PY_NAME} npm launcher ${pkg.version} (runs ${PY_SPEC})\n`);
    return;
  }

  let uv = findUv();
  if (!uv) uv = await installUv();
  if (uv) {
    return run({ cmd: uv, args: ['tool', 'run', '--from', PY_SPEC, PY_NAME, ...args] });
  }

  const fallback = viaPip(args);
  if (fallback) return run(fallback);

  log('could not find or install uv, and the Python fallback did not work.');
  log('Install uv (https://docs.astral.sh/uv/) or Python, then run again.');
  log('Details: https://github.com/ilyautov/marketplaces-mcp-ru#установка');
  process.exit(1);
}

main().catch((err) => {
  log(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
