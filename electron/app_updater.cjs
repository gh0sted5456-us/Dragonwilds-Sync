const fs = require('fs');
const path = require('path');
const https = require('https');
const crypto = require('crypto');

const USER_AGENT = 'DragonwildsSync/1.0';
const MAX_REDIRECTS = 6;
const DOWNLOAD_HOSTS = new Set(['github.com', 'objects.githubusercontent.com', 'release-assets.githubusercontent.com', 'github-releases.githubusercontent.com']);

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

function assertAllowedDownloadUrl(value) {
  let url;
  try { url = new URL(String(value || '')); } catch (_) { throw new Error('Update download URL is invalid.'); }
  if (url.protocol !== 'https:' || !DOWNLOAD_HOSTS.has(url.hostname.toLowerCase())) throw new Error('Update download was redirected outside the trusted GitHub asset hosts.');
  return url;
}

function semverParts(value) {
  const m = String(value || '').trim().replace(/^v/i, '').match(/^(\d+)\.(\d+)(?:\.(\d+))?(?:[-+].*)?$/);
  return m ? [Number(m[1]), Number(m[2]), Number(m[3] || 0)] : null;
}
function isNewer(candidate, current) {
  const a = semverParts(candidate), b = semverParts(current);
  if (!a || !b) return false;
  for (let i = 0; i < 3; i++) { if (a[i] !== b[i]) return a[i] > b[i]; }
  return false;
}
function detectMode(app) {
  if (!app.isPackaged) return 'development';
  if (process.platform === 'linux') return process.env.APPIMAGE ? 'appimage' : 'linux-package';
  return 'portable';
}
function chooseAsset(release, platform = process.platform) {
  const assets = Array.isArray(release.assets) ? release.assets : [];
  if (platform === 'linux') return assets.find((a) => /\.AppImage$/i.test(String(a.name || ''))) || null;
  const exes = assets.filter((a) => /\.exe$/i.test(String(a.name || '')));
  return exes.find((a) => /portable/i.test(a.name))
    || exes.find((a) => !/(setup|installer|headless)/i.test(a.name))
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
    try { assertAllowedDownloadUrl(url); } catch (error) { reject(error); return; }
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
function safeAssetName(value) {
  const name = path.basename(String(value || '')).replace(/[^A-Za-z0-9_. ()-]/g, '_').trim();
  if (!name || !/\.(?:exe|AppImage)$/i.test(name)) throw new Error('The release asset does not have a supported portable filename.');
  return name;
}

function uniqueDownloadPath(directory, name, expectedDigest = '') {
  const parsed = path.parse(name);
  for (let index = 0; index < 1000; index += 1) {
    const candidate = path.join(directory, index ? `${parsed.name} (${index})${parsed.ext}` : name);
    if (!fs.existsSync(candidate)) return { path: candidate, alreadyDownloaded: false };
    if (expectedDigest) {
      try {
        if (sha256File(candidate) === expectedDigest) return { path: candidate, alreadyDownloaded: true };
      } catch (_) {}
    }
  }
  throw new Error('Downloads already contains too many files with this update name. Move or remove the older copies and try again.');
}

async function stageAndApply({ app, release, repositoryUrl }) {
  if (!app.isPackaged) throw new Error('Application updating is disabled in development mode.');
  if (!['win32', 'linux'].includes(process.platform)) throw new Error(`Portable application downloads are not available on ${process.platform}.`);
  const repository = normalizeRepository(repositoryUrl);
  const mode = detectMode(app);
  const asset = release?.asset;
  const expected = process.platform === 'linux' ? 'Linux AppImage' : 'Portable Windows EXE';
  if (!asset?.url || !asset?.name) throw new Error(`The GitHub release does not contain a ${expected} asset.`);
  const assetUrl = assertAllowedDownloadUrl(asset.url);
  const expectedPrefix = `/${repository.owner}/${repository.repo}/releases/download/`.toLowerCase();
  if (assetUrl.hostname.toLowerCase() !== 'github.com' || !assetUrl.pathname.toLowerCase().startsWith(expectedPrefix)) throw new Error('Update blocked: the selected asset does not belong to the configured Dragonwilds Sync release repository.');
  if (!asset.digest) throw new Error('Update blocked: the selected GitHub release asset does not publish a SHA-256 digest.');
  const expectedDigest = String(asset.digest).toLowerCase();
  const downloads = app.getPath('downloads');
  fs.mkdirSync(downloads, { recursive: true });
  const selected = uniqueDownloadPath(downloads, safeAssetName(asset.name), expectedDigest);
  const currentExe = process.platform === 'linux' ? String(process.env.APPIMAGE || process.execPath) : String(process.env.PORTABLE_EXECUTABLE_FILE || process.execPath);
  if (!currentExe || !fs.existsSync(currentExe)) throw new Error(`The running ${expected} path could not be resolved.`);
  let actual = expectedDigest;
  if (!selected.alreadyDownloaded) {
    const temporary = `${selected.path}.download-${process.pid}-${Date.now()}`;
    try {
      await downloadFile(asset.url, temporary);
      actual = sha256File(temporary);
      if (actual !== expectedDigest) throw new Error('Update blocked: downloaded asset SHA-256 does not match GitHub release metadata.');
      fs.renameSync(temporary, selected.path);
      if (process.platform === 'linux') fs.chmodSync(selected.path, 0o755);
    } catch (error) {
      try { fs.unlinkSync(temporary); } catch (_) {}
      throw error;
    }
  }
  return {
    ok: true,
    mode,
    manualInstall: true,
    downloaded: selected.path,
    alreadyDownloaded: selected.alreadyDownloaded,
    currentExecutable: currentExe,
    targetVersion: release.latestVersion,
    sha256: actual,
    instructions: process.platform === 'linux'
      ? 'Close Dragonwilds Sync, replace the current AppImage with this verified download, preserve executable permission, then launch it.'
      : 'Close Dragonwilds Sync, replace the current portable EXE with this verified download, then launch the replacement.',
  };
}

function readAppliedUpdate(app) {
  const marker = path.join(app.getPath('userData'), 'update-result.json');
  const failureMarker = path.join(app.getPath('userData'), 'update-failure.txt');
  try {
    const message = fs.readFileSync(failureMarker, 'utf8').trim();
    if (message) return { ok: false, failed: true, message, marker: true };
  } catch (_) {}
  try {
    const data = JSON.parse(fs.readFileSync(marker, 'utf8'));
    if (String(data.version || '').replace(/^v/i, '') !== String(app.getVersion() || '').replace(/^v/i, '')) return null;
    return { ok: true, ...data, marker: true };
  } catch (_) { return null; }
}
function dismissAppliedUpdate(app) {
  let removed = false;
  for (const name of ['update-result.json', 'update-failure.txt']) {
    try { fs.unlinkSync(path.join(app.getPath('userData'), name)); removed = true; } catch (_) {}
  }
  return removed;
}

module.exports = { normalizeRepository, checkForUpdates, stageAndApply, detectMode, readAppliedUpdate, dismissAppliedUpdate, isNewer, chooseAsset, uniqueDownloadPath, assertAllowedDownloadUrl };
