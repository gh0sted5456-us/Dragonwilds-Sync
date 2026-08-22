const fs = require('fs');
const path = require('path');
const os = require('os');
const https = require('https');
const crypto = require('crypto');
const { spawn } = require('child_process');

const USER_AGENT = 'DragonwildsSync/1.0';
const MAX_REDIRECTS = 6;

function normalizeRepository(input) {
  const raw = String(input || '').trim();
  if (!raw) throw new Error('Application GitHub repository is not configured.');
  let owner = '', repo = '';
  if (/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(raw)) {
    [owner, repo] = raw.split('/');
  } else {
    let url;
    try { url = new URL(raw); } catch (_) { throw new Error('Enter a GitHub repository URL such as https://github.com/owner/repo.'); }
    if (url.protocol !== 'https:' || url.hostname.toLowerCase() !== 'github.com') throw new Error('Application updates must use an HTTPS github.com repository URL.');
    const parts = url.pathname.split('/').filter(Boolean);
    if (parts.length < 2) throw new Error('GitHub repository URL must include owner/repository.');
    owner = parts[0]; repo = parts[1].replace(/\.git$/i, '');
  }
  return { owner, repo, repository: `https://github.com/${owner}/${repo}` };
}

function requestJson(url, headers = {}, redirects = 0) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: { 'User-Agent': USER_AGENT, 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2026-03-10', ...headers } }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location && redirects < MAX_REDIRECTS) {
        res.resume(); return resolve(requestJson(new URL(res.headers.location, url).toString(), headers, redirects + 1));
      }
      let data = ''; res.setEncoding('utf8');
      res.on('data', (chunk) => { data += chunk; if (data.length > 8 * 1024 * 1024) req.destroy(new Error('GitHub response exceeded the safety limit.')); });
      res.on('end', () => {
        if (res.statusCode === 304) return resolve({ status: 304, headers: res.headers, data: null });
        if (res.statusCode < 200 || res.statusCode >= 300) return reject(new Error(`GitHub update check failed (${res.statusCode}).`));
        try { resolve({ status: res.statusCode, headers: res.headers, data: JSON.parse(data) }); } catch (_) { reject(new Error('GitHub returned invalid release metadata.')); }
      });
    });
    req.setTimeout(15000, () => req.destroy(new Error('GitHub update check timed out.')));
    req.on('error', reject);
  });
}

function semverParts(value) {
  const m = String(value || '').trim().replace(/^v/i, '').match(/^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$/);
  return m ? m.slice(1).map(Number) : null;
}
function isNewer(candidate, current) {
  const a = semverParts(candidate), b = semverParts(current);
  if (!a || !b) return false;
  for (let i = 0; i < 3; i++) { if (a[i] !== b[i]) return a[i] > b[i]; }
  return false;
}
function detectMode(app) {
  if (!app.isPackaged) return 'development';
  return 'portable';
}
function chooseAsset(release) {
  const assets = Array.isArray(release.assets) ? release.assets : [];
  const exes = assets.filter((a) => /\.exe$/i.test(String(a.name || '')));
  return exes.find((a) => /portable/i.test(a.name))
    || exes.find((a) => !/(setup|installer)/i.test(a.name))
    || null;
}
function normalizeDigest(asset) {
  const raw = String(asset?.digest || '').trim();
  const m = raw.match(/^sha256:([a-f0-9]{64})$/i);
  return m ? m[1].toLowerCase() : '';
}

async function checkForUpdates({ repositoryUrl, currentVersion, mode, etag = '' }) {
  const repo = normalizeRepository(repositoryUrl);
  const apiUrl = `https://api.github.com/repos/${encodeURIComponent(repo.owner)}/${encodeURIComponent(repo.repo)}/releases/latest`;
  const headers = etag ? { 'If-None-Match': etag } : {};
  const response = await requestJson(apiUrl, headers);
  if (response.status === 304) return { ok: true, notModified: true, repository: repo.repository, etag };
  const release = response.data || {};
  const tag = String(release.tag_name || '').trim();
  const asset = chooseAsset(release);
  return {
    ok: true,
    repository: repo.repository,
    etag: String(response.headers.etag || ''),
    currentVersion: String(currentVersion || ''),
    latestVersion: tag.replace(/^v/i, ''),
    tag,
    available: isNewer(tag, currentVersion),
    mode,
    name: String(release.name || tag || 'Release'),
    notes: String(release.body || '').slice(0, 12000),
    publishedAt: String(release.published_at || ''),
    releaseUrl: String(release.html_url || repo.repository),
    asset: asset ? { name: asset.name, url: asset.browser_download_url, size: Number(asset.size || 0), digest: normalizeDigest(asset) } : null,
  };
}

function downloadFile(url, destination, redirects = 0) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: { 'User-Agent': USER_AGENT, 'Accept': 'application/octet-stream' } }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location && redirects < MAX_REDIRECTS) {
        res.resume(); return resolve(downloadFile(new URL(res.headers.location, url).toString(), destination, redirects + 1));
      }
      if (res.statusCode < 200 || res.statusCode >= 300) { res.resume(); return reject(new Error(`Update download failed (${res.statusCode}).`)); }
      fs.mkdirSync(path.dirname(destination), { recursive: true });
      const out = fs.createWriteStream(destination, { flags: 'w' });
      res.pipe(out); out.on('finish', () => out.close(() => resolve(destination))); out.on('error', reject);
    });
    req.setTimeout(120000, () => req.destroy(new Error('Update download timed out.')));
    req.on('error', reject);
  });
}
function sha256File(file) {
  const hash = crypto.createHash('sha256');
  const fd = fs.openSync(file, 'r');
  const buffer = Buffer.alloc(1024 * 1024);
  try { let count; while ((count = fs.readSync(fd, buffer, 0, buffer.length, null)) > 0) hash.update(buffer.subarray(0, count)); }
  finally { fs.closeSync(fd); }
  return hash.digest('hex');
}
function psQuote(value) { return `'${String(value).replace(/'/g, "''")}'`; }

async function stageAndApply({ app, release, repositoryUrl }) {
  if (!app.isPackaged) throw new Error('Application updating is disabled in development mode.');
  if (process.platform !== 'win32') throw new Error('Dragonwilds Sync 2.5.0 updates require the Windows portable application.');
  const mode = detectMode(app);
  const asset = release?.asset;
  if (!asset?.url || !asset?.name) throw new Error('The GitHub release does not contain a Portable Windows EXE asset.');
  if (!asset.digest) throw new Error('Update blocked: the selected GitHub release asset does not publish a SHA-256 digest.');
  const updateDir = path.join(app.getPath('userData'), 'updates'); fs.mkdirSync(updateDir, { recursive: true });
  const staged = path.join(updateDir, path.basename(asset.name).replace(/[^A-Za-z0-9_. -]/g, '_'));
  await downloadFile(asset.url, staged);
  const actual = sha256File(staged);
  if (actual !== String(asset.digest).toLowerCase()) { try { fs.unlinkSync(staged); } catch (_) {} throw new Error('Update blocked: downloaded asset SHA-256 does not match GitHub release metadata.'); }

  const marker = path.join(app.getPath('userData'), 'update-result.json');
  fs.writeFileSync(marker, JSON.stringify({ version: release.latestVersion, name: release.name, notes: release.notes, releaseUrl: release.releaseUrl, repository: repositoryUrl, appliedAtUtc: new Date().toISOString(), mode }, null, 2));
  const currentExe = process.env.PORTABLE_EXECUTABLE_FILE || process.execPath;
  const script = path.join(os.tmpdir(), `DragonwildsSync_Update_${Date.now()}.ps1`);
  const body = `$ErrorActionPreference='Stop'\n$pidToWait=${process.pid}\n$src=${psQuote(staged)}\n$dst=${psQuote(currentExe)}\ntry { Wait-Process -Id $pidToWait -ErrorAction SilentlyContinue } catch {}\nStart-Sleep -Milliseconds 600\nCopy-Item -LiteralPath $src -Destination $dst -Force\nRemove-Item -LiteralPath $src -Force -ErrorAction SilentlyContinue\nStart-Process -FilePath $dst\nRemove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue\n`;
  fs.writeFileSync(script, body, 'utf8');
  const child = spawn('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script], { detached: true, stdio: 'ignore', windowsHide: true });
  child.unref();
  setTimeout(() => app.quit(), 250);
  return { ok: true, mode, staged, targetVersion: release.latestVersion };
}

function readAppliedUpdate(app) {
  const marker = path.join(app.getPath('userData'), 'update-result.json');
  try {
    const data = JSON.parse(fs.readFileSync(marker, 'utf8'));
    if (String(data.version || '').replace(/^v/i, '') !== String(app.getVersion() || '').replace(/^v/i, '')) return null;
    return { ...data, marker: true };
  } catch (_) { return null; }
}
function dismissAppliedUpdate(app) {
  const marker = path.join(app.getPath('userData'), 'update-result.json');
  try { fs.unlinkSync(marker); return true; } catch (_) { return false; }
}

module.exports = { normalizeRepository, checkForUpdates, stageAndApply, detectMode, readAppliedUpdate, dismissAppliedUpdate };
