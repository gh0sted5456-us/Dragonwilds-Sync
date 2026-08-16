const { app, safeStorage, shell } = require('electron');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const os = require('os');
const { execFileSync } = require('child_process');

const GAME_DOMAIN = 'runescapedragonwilds';
const API_ROOT = 'https://api.nexusmods.com/v1';
const SSO_ROOT = 'wss://sso.nexusmods.com';
const WEB_ROOT = 'https://www.nexusmods.com';
const CACHE_TTL_MS = 15 * 60 * 1000;

function ensureDir(dir) { fs.mkdirSync(dir, { recursive: true }); return dir; }
function readJson(file, fallback = {}) { try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch (_) { return fallback; } }
function writeJson(file, data) { ensureDir(path.dirname(file)); fs.writeFileSync(file, JSON.stringify(data, null, 2), 'utf8'); }
function normalizeInt(value) { const n = Number(value); return Number.isFinite(n) && n > 0 ? Math.trunc(n) : null; }

class NexusAdapter {
  constructor() {
    this.sessionKey = '';
    this.ssoPending = null;
  }
  get secureFile() { return path.join(app.getPath('userData'), 'secure', 'nexus-auth.json'); }
  get cacheFile() { return path.join(app.getPath('userData'), 'cache', 'nexus-metadata.json'); }
  get stagingDir() { return ensureDir(path.join(app.getPath('userData'), 'Nexus', 'Staging')); }
  get appId() {
    const env = String(process.env.DWSYNC_NEXUS_APP_ID || '').trim();
    if (env) return env;
    const candidates = [
      path.join(app.isPackaged ? process.resourcesPath : path.resolve(__dirname, '..'), 'resources', 'nexus-app.json'),
      path.join(path.resolve(__dirname, '..'), 'resources', 'nexus-app.json'),
    ];
    for (const file of candidates) {
      const cfg = readJson(file, {});
      if (cfg && cfg.appid) return String(cfg.appid).trim();
    }
    return '';
  }
  readAuthMeta() {
    const data = readJson(this.secureFile, {});
    return { username: data.username || '', user_id: data.user_id || null, auth_type: data.auth_type || '', connected_at: data.connected_at || '', application_slug: data.application_slug || this.appId || '' };
  }
  getApiKey() {
    if (this.sessionKey) return this.sessionKey;
    const data = readJson(this.secureFile, {});
    if (!data.encrypted_key) return '';
    try {
      if (!safeStorage.isEncryptionAvailable()) return '';
      return safeStorage.decryptString(Buffer.from(String(data.encrypted_key), 'base64'));
    } catch (_) { return ''; }
  }
  saveKey(apiKey, account = {}, authType = 'sso') {
    const key = String(apiKey || '').trim();
    if (!key) throw new Error('Nexus API key is empty.');
    const record = {
      username: account.name || account.username || '',
      user_id: account.user_id || account.userId || null,
      auth_type: authType,
      connected_at: new Date().toISOString(),
      application_slug: this.appId || '',
      encrypted_key: '',
    };
    if (safeStorage.isEncryptionAvailable()) {
      record.encrypted_key = safeStorage.encryptString(key).toString('base64');
      writeJson(this.secureFile, record);
      this.sessionKey = '';
    } else {
      // Never write Nexus credentials in plaintext. Keep it session-only when OS encryption is unavailable.
      this.sessionKey = key;
      writeJson(this.secureFile, { ...record, encrypted_key: '', session_only: true });
    }
    return record;
  }
  disconnect() {
    this.sessionKey = '';
    try { fs.unlinkSync(this.secureFile); } catch (_) {}
    return this.status();
  }
  async request(endpoint, { method = 'GET', body = null, keyRequired = true } = {}) {
    const key = this.getApiKey();
    if (keyRequired && !key) throw new Error('Connect a Nexus Mods account first.');
    const headers = { 'Accept': 'application/json', 'Application-Name': 'Dragonwilds-Sync', 'Application-Version': app.getVersion() || '0.0.0' };
    if (key) headers.apikey = key;
    if (body) headers['Content-Type'] = 'application/json';
    const response = await fetch(`${API_ROOT}${endpoint}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
    const remainingDaily = response.headers.get('x-rl-daily-remaining');
    const remainingHourly = response.headers.get('x-rl-hourly-remaining');
    let data = null;
    const text = await response.text();
    if (text) { try { data = JSON.parse(text); } catch (_) { data = text; } }
    if (!response.ok) {
      const msg = typeof data === 'object' && data ? (data.message || data.error || JSON.stringify(data)) : String(data || response.statusText);
      const error = new Error(`Nexus Mods: ${msg}`);
      error.status = response.status;
      throw error;
    }
    return { data, rate: { daily_remaining: remainingDaily == null ? null : Number(remainingDaily), hourly_remaining: remainingHourly == null ? null : Number(remainingHourly) } };
  }
  async validateKey(apiKey = '') {
    const previous = this.sessionKey;
    if (apiKey) this.sessionKey = String(apiKey).trim();
    try {
      const { data, rate } = await this.request('/users/validate.json');
      return { account: data || {}, rate };
    } finally { if (apiKey) this.sessionKey = previous; }
  }
  async connectDevelopmentKey(apiKey) {
    const key = String(apiKey || '').trim();
    if (!key) throw new Error('Enter a Nexus personal API key for development/testing.');
    const previous = this.sessionKey;
    this.sessionKey = key;
    try {
      const result = await this.validateKey();
      this.saveKey(key, result.account, 'development_key');
      return this.status({ rate: result.rate });
    } catch (error) {
      this.sessionKey = previous;
      throw error;
    }
  }
  async connectSSO() {
    const appid = this.appId;
    if (!appid) throw new Error('This build is not yet registered with Nexus Mods. Set DWSYNC_NEXUS_APP_ID for a registered test build, or use a personal API key under Developer Options.');
    let WebSocketImpl = null;
    try { WebSocketImpl = require('ws'); } catch (_) { throw new Error('Nexus SSO support is not installed in this development checkout. Run npm install so the bundled ws dependency is available.'); }
    if (this.ssoPending) throw new Error('A Nexus authorization request is already open.');
    const id = crypto.randomUUID();
    const authorizeUrl = `${WEB_ROOT}/sso?id=${encodeURIComponent(id)}`;
    return await new Promise((resolve, reject) => {
      const socket = new WebSocketImpl(SSO_ROOT);
      let timer = null;
      let ping = null;
      const done = (err, value) => {
        clearTimeout(timer); clearInterval(ping); this.ssoPending = null;
        try { socket.close(); } catch (_) {}
        err ? reject(err) : resolve(value);
      };
      this.ssoPending = { id, socket };
      timer = setTimeout(() => done(new Error('Nexus authorization timed out. You can try Connect again.')), 5 * 60 * 1000);
      socket.on('open', async () => {
        socket.send(JSON.stringify({ id, appid }));
        ping = setInterval(() => { try { socket.ping(); } catch (_) {} }, 30000);
        await shell.openExternal(authorizeUrl);
      });
      socket.on('message', async (raw) => {
        const key = String(raw || '').trim();
        if (!key) return;
        try {
          const previous = this.sessionKey; this.sessionKey = key;
          const result = await this.validateKey();
          this.sessionKey = previous;
          this.saveKey(key, result.account, 'sso');
          done(null, this.status({ rate: result.rate }));
        } catch (error) { done(error); }
      });
      socket.on('error', (error) => done(error));
      socket.on('close', () => { if (this.ssoPending) done(new Error('Nexus authorization window closed before authorization completed.')); });
    });
  }
  status(extra = {}) {
    const key = this.getApiKey();
    const meta = this.readAuthMeta();
    return {
      connected: !!key,
      username: meta.username || '',
      user_id: meta.user_id || null,
      auth_type: meta.auth_type || '',
      connected_at: meta.connected_at || '',
      registered_app: !!this.appId,
      secure_storage: safeStorage.isEncryptionAvailable(),
      game_domain: GAME_DOMAIN,
      ...extra,
    };
  }
  cache() { return readJson(this.cacheFile, { mods: {}, searches: {}, files: {}, checked_at: '' }); }
  saveCache(cache) { cache.checked_at = new Date().toISOString(); writeJson(this.cacheFile, cache); }
  modUrl(modId) { return `${WEB_ROOT}/${GAME_DOMAIN}/mods/${Number(modId)}`; }
  fileUrl(modId) { return `${this.modUrl(modId)}?tab=files`; }
  async getMod(modId, { force = false } = {}) {
    const id = normalizeInt(modId); if (!id) throw new Error('Nexus Mod ID is required.');
    const cache = this.cache(); const cached = cache.mods?.[id];
    if (!force && cached && Date.now() - Number(cached.cached_at || 0) < CACHE_TTL_MS) return { ...cached.data, cached: true };
    const { data, rate } = await this.request(`/games/${GAME_DOMAIN}/mods/${id}.json`);
    cache.mods = cache.mods || {}; cache.mods[id] = { cached_at: Date.now(), data }; this.saveCache(cache);
    return { ...data, cached: false, rate };
  }
  async getFiles(modId, { force = false } = {}) {
    const id = normalizeInt(modId); if (!id) throw new Error('Nexus Mod ID is required.');
    const cache = this.cache(); const cached = cache.files?.[id];
    if (!force && cached && Date.now() - Number(cached.cached_at || 0) < CACHE_TTL_MS) return { ...cached.data, cached: true };
    const { data, rate } = await this.request(`/games/${GAME_DOMAIN}/mods/${id}/files.json`);
    cache.files = cache.files || {}; cache.files[id] = { cached_at: Date.now(), data }; this.saveCache(cache);
    return { ...(data || {}), cached: false, rate };
  }
  async search(query, { force = false } = {}) {
    // Nexus REST v1 has no general text-search endpoint. Use a cached/curated discovery
    // fallback from the public game listing through Nexus's own website, then resolve
    // selected Mod IDs through the authenticated API. This avoids scraping credentials
    // or inventing an undocumented API contract.
    const q = String(query || '').trim();
    const url = q ? `${WEB_ROOT}/${GAME_DOMAIN}/mods/?search=${encodeURIComponent(q)}` : `${WEB_ROOT}/${GAME_DOMAIN}/mods/`;
    return { mode: 'interactive', query: q, url, results: [], message: 'Search opens Nexus Mods in your browser. Paste or Link a Nexus Mod ID to hydrate authenticated metadata in Dragonwilds Sync.' };
  }
  async downloadDescriptor(modId, fileId) {
    const mid = normalizeInt(modId), fid = normalizeInt(fileId);
    if (!mid || !fid) throw new Error('Nexus Mod ID and File ID are required.');
    if (!this.getApiKey()) return { mode:'browser', url:this.fileUrl(mid), mod_id:mid, file_id:fid, message:'Connect Nexus for API-assisted downloads, or complete the normal Nexus website download.' };
    try {
      const { data, rate } = await this.request(`/games/${GAME_DOMAIN}/mods/${mid}/files/${fid}/download_link.json`);
      const links = Array.isArray(data) ? data : [];
      const uri = links.find((item) => item && (item.URI || item.uri))?.URI || links.find((item) => item && (item.URI || item.uri))?.uri || '';
      if (uri) return { mode: 'direct', url: uri, rate, mod_id: mid, file_id: fid };
    } catch (error) {
      if (![401, 403, 404].includes(Number(error.status))) throw error;
    }
    return { mode: 'browser', url: this.fileUrl(mid), mod_id: mid, file_id: fid, message: 'Nexus requires this file to be acquired through its website/account download flow.' };
  }
  async downloadToStaging(url, suggestedName = 'nexus-mod.zip') {
    const parsed = new URL(String(url || ''));
    if (!['https:'].includes(parsed.protocol)) throw new Error('Nexus direct downloads must use HTTPS.');
    const response = await fetch(parsed.toString(), { redirect: 'follow' });
    if (!response.ok) throw new Error(`Nexus download failed (${response.status}).`);
    const buffer = Buffer.from(await response.arrayBuffer());
    if (!buffer.length) throw new Error('Nexus returned an empty download.');
    const safe = String(suggestedName || 'nexus-mod.zip').replace(/[^A-Za-z0-9._ -]/g, '_');
    const target = path.join(this.stagingDir, `${Date.now()}-${safe}`);
    fs.writeFileSync(target, buffer);
    return { path: target, sha256: crypto.createHash('sha256').update(buffer).digest('hex'), size: buffer.length };
  }
  prepareArchive(sourcePath) {
    const source = path.resolve(String(sourcePath || ''));
    if (!fs.existsSync(source) || !fs.statSync(source).isFile()) throw new Error('The downloaded Nexus archive was not found.');
    const extension = path.extname(source).toLowerCase();
    if (extension === '.zip') return { path: source, converted: false };
    if (extension !== '.7z') throw new Error('Dragonwilds Sync accepts Nexus ZIP and 7z archives.');
    const { path7za } = require('7zip-bin');
    const work = fs.mkdtempSync(path.join(os.tmpdir(), 'dws-nexus-'));
    const extracted = path.join(work, 'extracted');
    const converted = path.join(this.stagingDir, `${Date.now()}-${path.basename(source, extension).replace(/[^A-Za-z0-9._ -]/g, '_')}.zip`);
    fs.mkdirSync(extracted, { recursive: true });
    try {
      execFileSync(path7za, ['x', source, `-o${extracted}`, '-y', '-bd'], { windowsHide: true, stdio: 'pipe' });
      const entries = fs.readdirSync(extracted);
      if (!entries.length) throw new Error('The 7z archive is empty.');
      execFileSync(path7za, ['a', '-tzip', converted, path.join(extracted, '*'), '-y', '-bd'], { windowsHide: true, stdio: 'pipe' });
      if (!fs.existsSync(converted) || !fs.statSync(converted).size) throw new Error('The 7z archive could not be converted for inspection.');
      return { path: converted, converted: true, source_path: source };
    } catch (error) {
      try { fs.rmSync(converted, { force: true }); } catch (_) {}
      throw new Error(`Could not unpack the Nexus 7z archive: ${String(error?.message || error)}`);
    } finally {
      try { fs.rmSync(work, { recursive: true, force: true }); } catch (_) {}
    }
  }
}

module.exports = { NexusAdapter, GAME_DOMAIN };
