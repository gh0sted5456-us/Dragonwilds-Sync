// Optional, user-consented cloud publishing. OAuth tokens live only in the
// Electron main process, encrypted with the current OS user's safeStorage key.
// The Next.js UI and remote-access API never receive tokens or client secrets.
const fs = require("fs");
const path = require("path");
const http = require("http");
const crypto = require("crypto");

const SCHEMA = "RSDWSync.CloudManifest.v1";
const CHUNK = 10 * 1024 * 1024; // 32 × 320 KiB, valid for OneDrive upload sessions.
const PROVIDERS = {
  google: {
    authorize: "https://accounts.google.com/o/oauth2/v2/auth",
    token: "https://oauth2.googleapis.com/token",
    scope: "https://www.googleapis.com/auth/drive.file",
  },
  onedrive: {
    authorize: "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    token: "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    scope: "Files.ReadWrite offline_access",
  },
};

function authorizeUrl(provider, clientId, redirectUri, state, verifier) {
  const info = PROVIDERS[provider];
  if (!info || !/^[A-Za-z0-9._-]{8,256}$/.test(String(clientId || ""))) throw new Error("Enter a valid Google or Microsoft OAuth client ID");
  const url = new URL(info.authorize);
  for (const [key, value] of Object.entries({
    client_id: clientId, response_type: "code", redirect_uri: redirectUri,
    scope: info.scope, state, code_challenge: crypto.createHash("sha256").update(verifier).digest("base64url"),
    code_challenge_method: "S256",
  })) url.searchParams.set(key, value);
  if (provider === "google") { url.searchParams.set("access_type", "offline"); url.searchParams.set("prompt", "consent"); }
  return url.toString();
}

function safeTarget(target) {
  const parts = String(target || "").replace(/\\/g, "/").split("/");
  if (parts[0] !== "RSDragonwilds" || parts.some((part) => !part || part === "." || part === ".." || /[<>:"|?*\x00-\x1f]/.test(part))) throw new Error("Invalid exported mod path");
  return parts;
}

function validateExport(dataDir, worldId, exportFolder) {
  const id = String(worldId || "");
  if (!/^[A-Za-z0-9_-]{1,120}$/.test(id)) throw new Error("Invalid Server profile ID");
  const base = path.resolve(dataDir, "delivery-exports", id);
  const folder = path.resolve(String(exportFolder || ""));
  if (!folder.toLowerCase().startsWith((base + path.sep).toLowerCase()) || !fs.statSync(folder).isDirectory()) throw new Error("Choose a verified export from this Server profile");
  if (!fs.realpathSync(folder).toLowerCase().startsWith((fs.realpathSync(base) + path.sep).toLowerCase())) throw new Error("Cloud export folder is linked outside this profile");
  const manifest = JSON.parse(fs.readFileSync(path.join(folder, "rsdw-manifest.json"), "utf8"));
  if (manifest.schema !== SCHEMA || !Array.isArray(manifest.files) || manifest.files.length > 50000) throw new Error("The prepared cloud manifest is invalid");
  const files = manifest.files.map((entry) => {
    const parts = safeTarget(entry.target);
    const source = path.resolve(folder, ...parts);
    if (!source.toLowerCase().startsWith((folder + path.sep).toLowerCase()) || !fs.statSync(source).isFile()) throw new Error("A prepared cloud file is missing");
    if (!fs.realpathSync(source).toLowerCase().startsWith((fs.realpathSync(folder) + path.sep).toLowerCase())) throw new Error("A prepared cloud file is linked outside the export");
    if (fs.statSync(source).size !== Number(entry.size) || !/^[a-f0-9]{64}$/i.test(entry.sha256)) throw new Error("Prepared cloud file metadata does not match");
    return { ...entry, source };
  });
  return { folder, manifest, files };
}

async function digest(file) {
  const hash = crypto.createHash("sha256");
  for await (const chunk of fs.createReadStream(file)) hash.update(chunk);
  return hash.digest("hex");
}

class CloudPublisher {
  constructor({ dataDir, safeStorage, openExternal, fetchImpl = fetch, onProgress = () => {} }) {
    this.dataDir = dataDir;
    this.safeStorage = safeStorage;
    this.openExternal = openExternal;
    this.fetch = fetchImpl;
    this.onProgress = onProgress;
    this.vault = path.join(dataDir, "cloud-publisher.enc");
    this.busy = false;
  }

  assertEncryption() {
    if (!this.safeStorage.isEncryptionAvailable() || this.safeStorage.getSelectedStorageBackend?.() === "basic_text") {
      throw new Error("Secure OS credential storage is unavailable. Use manual cloud upload on this machine.");
    }
  }

  read() {
    this.assertEncryption();
    if (!fs.existsSync(this.vault)) return {};
    try { return JSON.parse(this.safeStorage.decryptString(fs.readFileSync(this.vault))); }
    catch (error) {
      const backup = `${this.vault}.previous`;
      if (!fs.existsSync(backup)) throw error;
      return JSON.parse(this.safeStorage.decryptString(fs.readFileSync(backup)));
    }
  }

  write(accounts) {
    this.assertEncryption();
    fs.mkdirSync(this.dataDir, { recursive: true });
    const temporary = `${this.vault}.${crypto.randomUUID()}.tmp`;
    const encrypted = this.safeStorage.encryptString(JSON.stringify(accounts));
    fs.writeFileSync(temporary, encrypted, { mode: 0o600 });
    try {
      if (fs.existsSync(this.vault)) fs.copyFileSync(this.vault, `${this.vault}.previous`);
      try { fs.renameSync(temporary, this.vault); }
      catch (error) {
        if (!["EPERM", "EACCES", "EXDEV"].includes(error.code)) throw error;
        // Packaged Windows app-data redirection can reject rename in place.
        // Keep the encrypted previous generation recoverable until verified.
        fs.copyFileSync(temporary, this.vault);
      }
      if (!fs.readFileSync(this.vault).equals(encrypted)) throw new Error("Encrypted cloud credential write could not be verified");
    } finally { try { fs.rmSync(temporary, { force: true }); } catch {} }
  }

  status() {
    try {
      const accounts = this.read();
      return { secure: true, providers: Object.fromEntries(Object.entries(PROVIDERS).map(([key]) => [key, {
        connected: !!accounts[key]?.refreshToken, clientIdHint: accounts[key]?.clientId ? `…${accounts[key].clientId.slice(-6)}` : null,
        auto: Object.fromEntries(Object.entries(accounts[key]?.auto || {}).map(([worldId, entry]) => [worldId, {
          enabled: !!entry.enabled, platform: entry.platform || "steam", lastVerifiedRevision: entry.lastVerifiedRevision || null,
          lastError: entry.lastError || null,
        }])),
      }])) };
    } catch (error) { return { secure: false, error: error.message, providers: {} }; }
  }

  async tokenRequest(provider, params) {
    const response = await this.fetch(PROVIDERS[provider].token, {
      method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(params), signal: AbortSignal.timeout(30000),
    });
    if (!response.ok) throw new Error(`${provider} authorization failed (${response.status}); check the client registration and consent`);
    return response.json();
  }

  async connect(provider, clientId) {
    this.assertEncryption();
    if (this.busy) throw new Error("Another cloud account operation is already running");
    if (!PROVIDERS[provider]) throw new Error("Choose Google Drive or OneDrive");
    this.busy = true;
    const verifier = crypto.randomBytes(48).toString("base64url");
    const state = crypto.randomBytes(32).toString("base64url");
    const host = provider === "onedrive" ? "localhost" : "127.0.0.1";
    const server = http.createServer();
    let timer;
    try {
      await new Promise((resolve, reject) => { server.once("error", reject); server.listen(0, host, resolve); });
      const redirectUri = `http://${host}:${server.address().port}`;
      const authorization = authorizeUrl(provider, String(clientId || "").trim(), redirectUri, state, verifier);
      const codePromise = new Promise((resolve, reject) => {
        timer = setTimeout(() => reject(new Error("Cloud sign-in timed out")), 5 * 60_000);
        server.on("request", (req, res) => {
          const url = new URL(req.url, redirectUri);
          if (url.pathname !== "/") { res.writeHead(404); res.end(); return; }
          if (url.searchParams.get("state") !== state) { res.writeHead(400); res.end("Invalid sign-in state"); return; }
          clearTimeout(timer);
          const code = url.searchParams.get("code");
          const error = url.searchParams.get("error");
          res.writeHead(code ? 200 : 400, { "Content-Type": "text/plain; charset=utf-8" });
          res.end(code ? "RSDW Sync cloud account connected. Return to the launcher." : "Cloud sign-in was cancelled or denied.");
          if (code) resolve(code); else reject(new Error(error || "Cloud sign-in was denied"));
        });
      });
      await this.openExternal(authorization);
      const code = await codePromise;
      const token = await this.tokenRequest(provider, { client_id: clientId, code, code_verifier: verifier, redirect_uri: redirectUri, grant_type: "authorization_code" });
      if (!token.refresh_token || !token.access_token) throw new Error("Provider did not grant offline write access");
      const accounts = this.read();
      accounts[provider] = { clientId, refreshToken: token.refresh_token, accessToken: token.access_token,
        expiresAt: Date.now() + Number(token.expires_in || 3600) * 1000, folders: {}, uploaded: {} };
      this.write(accounts);
      return this.status();
    } finally { clearTimeout(timer); server.close(); this.busy = false; }
  }

  disconnect(provider) {
    if (!PROVIDERS[provider]) throw new Error("Unknown cloud provider");
    const accounts = this.read();
    delete accounts[provider];
    this.write(accounts);
    try { fs.rmSync(`${this.vault}.previous`, { force: true }); } catch {}
    return this.status();
  }

  setAutoPublish(provider, worldId, enabled, platform = "steam", consent = false, verifiedRevision = null) {
    if (!PROVIDERS[provider]) throw new Error("Choose Google Drive or OneDrive");
    if (!/^[A-Za-z0-9_-]{1,120}$/.test(String(worldId || ""))) throw new Error("Invalid Server profile ID");
    if (!["steam", "gamepass"].includes(platform)) throw new Error("Choose Steam or Game Pass files");
    const accounts = this.read();
    const account = accounts[provider];
    if (!account?.refreshToken) throw new Error("Connect this cloud account first");
    if (enabled && (!consent || !verifiedRevision || verifiedRevision !== account.published?.[worldId]?.revision)) {
      throw new Error("Publish and verify once, then explicitly approve automatic public updates");
    }
    account.auto ||= {};
    account.auto[worldId] = { enabled: !!enabled, platform,
      lastVerifiedRevision: enabled ? verifiedRevision : account.auto[worldId]?.lastVerifiedRevision || null, lastError: null };
    this.write(accounts);
    return this.status();
  }

  autoTasks() {
    const accounts = this.read();
    return Object.entries(accounts).flatMap(([provider, account]) => Object.entries(account.auto || {})
      .filter(([, task]) => task.enabled)
      .map(([worldId, task]) => ({ provider, worldId, platform: task.platform, lastVerifiedRevision: task.lastVerifiedRevision })));
  }

  autoResult(provider, worldId, revision, error = null) {
    const accounts = this.read();
    const task = accounts[provider]?.auto?.[worldId];
    if (!task) return;
    if (error) task.lastError = String(error.message || error).replace(/https?:\/\/\S+/gi, "[redacted]").slice(0, 400);
    else { task.lastVerifiedRevision = revision; task.lastError = null; }
    this.write(accounts);
  }

  async accessToken(provider, account) {
    if (account.accessToken && account.expiresAt > Date.now() + 60_000) return account.accessToken;
    const token = await this.tokenRequest(provider, { client_id: account.clientId, refresh_token: account.refreshToken, grant_type: "refresh_token", ...(provider === "onedrive" ? { scope: PROVIDERS[provider].scope } : {}) });
    if (!token.access_token) throw new Error("Cloud access expired. Reconnect this account.");
    account.accessToken = token.access_token;
    account.refreshToken = token.refresh_token || account.refreshToken;
    account.expiresAt = Date.now() + Number(token.expires_in || 3600) * 1000;
    const accounts = this.read(); accounts[provider] = account; this.write(accounts);
    return account.accessToken;
  }

  async request(provider, account, url, options = {}) {
    const token = await this.accessToken(provider, account);
    const response = await this.fetch(url, { ...options, redirect: "error", headers: { Authorization: `Bearer ${token}`, ...(options.headers || {}) }, signal: AbortSignal.timeout(120000) });
    if (!response.ok) throw new Error(`${provider} cloud request failed (${response.status})`);
    return response;
  }

  async folder(provider, account, worldId) {
    if (account.folders[worldId]) return account.folders[worldId];
    const name = `RSDW Sync - ${worldId}`;
    let response;
    if (provider === "google") {
      response = await this.request(provider, account, "https://www.googleapis.com/drive/v3/files?fields=id,name", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, mimeType: "application/vnd.google-apps.folder" }),
      });
    } else {
      response = await this.request(provider, account, "https://graph.microsoft.com/v1.0/me/drive/root/children", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, folder: {}, "@microsoft.graph.conflictBehavior": "rename" }),
      });
    }
    const result = await response.json();
    if (!result.id) throw new Error("Cloud folder creation returned no ID");
    account.folders[worldId] = result.id;
    const accounts = this.read(); accounts[provider] = account; this.write(accounts);
    return result.id;
  }

  async upload(provider, account, folderId, name, source) {
    const size = Buffer.isBuffer(source) ? source.length : fs.statSync(source).size;
    if (!size) throw new Error("Cannot publish an empty cloud file");
    const chunkAt = (start, length) => {
      if (Buffer.isBuffer(source)) return source.subarray(start, start + length);
      const buffer = Buffer.allocUnsafe(length);
      const fd = fs.openSync(source, "r");
      try {
        let read = 0;
        while (read < length) {
          const count = fs.readSync(fd, buffer, read, length - read, start + read);
          if (!count) throw new Error("Prepared cloud file changed during upload");
          read += count;
        }
      } finally { fs.closeSync(fd); }
      return buffer;
    };
    let uploadUrl;
    if (provider === "google") {
      const init = await this.request(provider, account, "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&fields=id,name,size", {
        method: "POST", headers: { "Content-Type": "application/json", "X-Upload-Content-Type": "application/octet-stream", "X-Upload-Content-Length": String(size) },
        body: JSON.stringify({ name, parents: [folderId] }),
      });
      uploadUrl = init.headers.get("location");
    } else {
      const encoded = encodeURIComponent(name);
      const init = await this.request(provider, account, `https://graph.microsoft.com/v1.0/me/drive/items/${encodeURIComponent(folderId)}:/${encoded}:/createUploadSession`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item: { "@microsoft.graph.conflictBehavior": "rename" } }),
      });
      uploadUrl = (await init.json()).uploadUrl;
    }
    if (!uploadUrl || new URL(uploadUrl).protocol !== "https:") throw new Error("Cloud provider returned an invalid upload session");
    let result = null;
    for (let start = 0; start < size; start += CHUNK) {
      const end = Math.min(size, start + CHUNK) - 1;
      // OneDrive uploadUrl already carries authorization. Never send a bearer
      // token to this dynamic host (Microsoft explicitly forbids it).
      const response = await this.fetch(uploadUrl, { method: "PUT", headers: {
        "Content-Length": String(end - start + 1), "Content-Range": `bytes ${start}-${end}/${size}`,
      }, body: chunkAt(start, end - start + 1), signal: AbortSignal.timeout(120000) });
      if (![200, 201, 202, 308].includes(response.status)) throw new Error(`${provider} upload failed (${response.status})`);
      if (response.status === 200 || response.status === 201) result = await response.json();
    }
    if (!result?.id) throw new Error("Cloud upload did not return a completed file ID");
    return result.id;
  }

  async share(provider, account, fileId) {
    if (provider === "google") {
      await this.request(provider, account, `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(fileId)}/permissions`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ type: "anyone", role: "reader" }),
      });
      return `https://drive.google.com/file/d/${encodeURIComponent(fileId)}/view`;
    }
    const response = await this.request(provider, account, `https://graph.microsoft.com/v1.0/me/drive/items/${encodeURIComponent(fileId)}/createLink`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ type: "view", scope: "anonymous" }),
    });
    const link = (await response.json()).link?.webUrl;
    if (!link) throw new Error("OneDrive did not permit an anonymous read-only link. Check the account or tenant sharing policy.");
    return link;
  }

  async publish(provider, worldId, exportFolder, consent) {
    if (!consent) throw new Error("Confirm public read-only sharing before publishing cloud files");
    if (this.busy) throw new Error("Another cloud account operation is already running");
    const accounts = this.read();
    const account = accounts[provider];
    if (!account?.refreshToken) throw new Error("Connect this cloud account first");
    const prepared = validateExport(this.dataDir, worldId, exportFolder);
    this.busy = true;
    try {
      const folderId = await this.folder(provider, account, worldId);
      const files = [];
      for (let index = 0; index < prepared.files.length; index++) {
        const file = prepared.files[index];
        this.onProgress({ provider, worldId, phase: "uploading", completed: index, total: prepared.files.length, target: file.target });
        if (await digest(file.source) !== String(file.sha256).toLowerCase()) throw new Error(`Prepared file changed after export: ${file.target}`);
        const key = `${file.size}:${String(file.sha256).toLowerCase()}`;
        let uploaded = account.uploaded[worldId]?.[key];
        if (!uploaded) {
          const name = `${file.sha256.slice(0, 24)}-${path.basename(file.target)}`;
          const id = await this.upload(provider, account, folderId, name, file.source);
          const url = await this.share(provider, account, id);
          uploaded = { id, url };
          if (!account.uploaded[worldId]) account.uploaded[worldId] = {};
          account.uploaded[worldId][key] = uploaded;
          const next = this.read(); next[provider] = account; this.write(next);
        }
        files.push({ target: file.target, size: file.size, sha256: file.sha256, url: uploaded.url });
      }
      const body = Buffer.from(JSON.stringify({ schema: SCHEMA, revision: prepared.manifest.revision, files }, null, 2) + "\n");
      const manifestId = await this.upload(provider, account, folderId, `rsdw-manifest-${crypto.randomBytes(6).toString("hex")}.json`, body);
      const manifestUrl = await this.share(provider, account, manifestId);
      account.published ||= {};
      account.published[worldId] = { revision: prepared.manifest.revision, at: Date.now() };
      const next = this.read(); next[provider] = account; this.write(next);
      this.onProgress({ provider, worldId, phase: "ready", completed: files.length, total: files.length, target: "" });
      return { manifestUrl, fileCount: files.length, provider, revision: prepared.manifest.revision };
    } finally { this.busy = false; }
  }
}

module.exports = { CloudPublisher, authorizeUrl, validateExport, safeTarget };
