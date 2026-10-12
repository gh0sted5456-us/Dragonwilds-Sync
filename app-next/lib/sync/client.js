const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { Readable, Transform } = require("stream");
const { pipeline } = require("stream/promises");
const dbm = require("../db");
const manifestLib = require("./manifest");
const cloudStorage = require("./cloud-storage");
const steamlib = require("../steamlibrary");
const { P } = require("../paths");
const profileSaves = require("../profile-saves");

const ledgerKey = (profileId) => `clientSyncLedger:${profileId}`;
const activeLedgerKey = (service, install = "") => {
  const location = path.resolve(String(install || service || "default")).toLowerCase();
  return `clientActiveSync:${service}:${crypto.createHash("sha256").update(location).digest("hex").slice(0, 12)}`;
};
const inFlight = new Map();
let syncQueue = Promise.resolve();

function safeLocal(install, target) {
  const relative = String(target || "").replace(/\\/g, "/");
  if (!relative.startsWith("RSDragonwilds/") || relative.split("/").some((part) => !part || part === "." || part === "..")) throw new Error("World manifest contains an unsafe mod path");
  const root = path.resolve(install) + path.sep;
  const local = path.resolve(install, ...relative.split("/"));
  if (!local.toLowerCase().startsWith(root.toLowerCase())) throw new Error("World manifest path escapes the game installation");
  return local;
}

function safeProfileSegment(value) {
  return String(value || "profile").replace(/[^a-zA-Z0-9_.-]/g, "_").slice(0, 120) || "profile";
}

function targetKey(value) {
  const normalized = String(value || "").replace(/\\/g, "/");
  return process.platform === "win32" ? normalized.toLowerCase() : normalized;
}

async function sha256File(file) {
  const hash = crypto.createHash("sha256");
  for await (const chunk of fs.createReadStream(file)) hash.update(chunk);
  return hash.digest("hex");
}

async function fetchJson(url, password, platform) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(url, { cache: "no-store", signal: controller.signal, headers: { "X-RSDW-World-Password": String(password || ""), "X-RSDW-Client-Platform": platform === "gamepass" ? "gamepass" : "steam" } });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.manifest) throw new Error(data.error || `World manifest request failed (${response.status})`);
    return data.manifest;
  } finally { clearTimeout(timeout); }
}

async function downloadChange(base, connection, platform, stagingRoot, change, onBytes = () => {}) {
  const local = safeLocal(stagingRoot, change.target);
  await fs.promises.mkdir(path.dirname(local), { recursive: true });
  const temp = `${local}.rsdw-sync-${crypto.randomBytes(6).toString("hex")}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120000);
  try {
    let downloadUrl = `${base}/file?target=${encodeURIComponent(change.target)}`;
    if (change.downloadUrl) {
      const candidate = new URL(change.downloadUrl);
      const expected = new URL(base);
      if (!["http:", "https:"].includes(candidate.protocol) || candidate.username || candidate.password || candidate.origin !== expected.origin) throw new Error("World manifest contains an unsafe download URL");
      downloadUrl = candidate.toString();
    }
    const attempt = async (requestUrl) => {
      let attemptBytes = 0;
      try {
        let response = await fetch(requestUrl, {
          cache: "no-store",
          signal: controller.signal,
          redirect: "manual",
          headers: { "X-RSDW-World-Password": String(connection.password || ""), "X-RSDW-Client-Platform": platform },
        });
        if (response.status >= 300 && response.status < 400 && response.headers.get("location")) {
          const cloudUrl = cloudStorage.normalizePublicUrl(response.headers.get("location"), change.storageProvider || "generic");
          response = await fetch(cloudUrl, { cache: "no-store", signal: controller.signal, redirect: "follow" });
        }
        if (!response.ok || !response.body) {
          const data = await response.json().catch(() => ({}));
          throw new Error(data.error || `Download failed (${response.status})`);
        }
        const contentLengthHeader = response.headers.get("content-length");
        const contentLength = contentLengthHeader == null ? null : Number(contentLengthHeader);
        if (contentLength !== null && Number.isFinite(contentLength) && contentLength !== change.size) throw new Error(`Size declaration changed while downloading ${change.target}`);
        const meter = new Transform({ transform(chunk, _encoding, callback) { attemptBytes += chunk.length; onBytes(chunk.length); callback(null, chunk); } });
        await pipeline(Readable.fromWeb(response.body), meter, fs.createWriteStream(temp, { flags: "wx" }));
        const stat = await fs.promises.stat(temp);
        if (stat.size !== change.size) throw new Error(`Size verification failed for ${change.target}`);
        if (await sha256File(temp) !== change.sha256) throw new Error(`Hash verification failed for ${change.target}`);
      } catch (error) {
        if (attemptBytes) onBytes(-attemptBytes);
        await fs.promises.rm(temp, { force: true }).catch(() => {});
        throw error;
      }
    };
    try { await attempt(downloadUrl); }
    catch (cloudError) {
      if (change.storageMode !== "hybrid") throw cloudError;
      const fallback = new URL(downloadUrl);
      fallback.searchParams.set("source", "local");
      await attempt(fallback.toString());
    }
    return { ...change, local, temp };
  } catch (error) {
    await fs.promises.rm(temp, { force: true }).catch(() => {});
    throw error;
  } finally { clearTimeout(timeout); }
}

async function mapLimit(items, limit, task) {
  const results = new Array(items.length);
  let cursor = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (cursor < items.length) {
      const index = cursor++;
      results[index] = await task(items[index], index);
    }
  });
  const settled = await Promise.allSettled(workers);
  const failed = settled.find((result) => result.status === "rejected");
  if (failed) throw failed.reason;
  return results;
}

function backupPath(root, target) {
  return path.join(root, "files", ...String(target).replace(/\\/g, "/").split("/"));
}

function writeReceipt(root, receipt) {
  fs.mkdirSync(root, { recursive: true });
  fs.writeFileSync(path.join(root, "receipt.json"), JSON.stringify(receipt, null, 2), "utf8");
}

async function saveProfileSnapshot(profileId, manifest, install, staged = []) {
  const permanent = P.clientProfile(profileId);
  const candidate = `${permanent}.candidate-${crypto.randomBytes(5).toString("hex")}`;
  const previous = `${permanent}.previous-${crypto.randomBytes(5).toString("hex")}`;
  await fs.promises.mkdir(candidate, { recursive: true });
  try {
    const stagedByTarget = new Map(staged.map((item) => [targetKey(item.target), item.temp]));
    for (const file of (manifest.units || []).flatMap((unit) => unit.files || [])) {
      const source = stagedByTarget.get(targetKey(file.target)) || safeLocal(install, file.target);
      const destination = safeLocal(candidate, file.target);
      await fs.promises.mkdir(path.dirname(destination), { recursive: true });
      await fs.promises.copyFile(source, destination);
    }
    await fs.promises.writeFile(path.join(candidate, "manifest.json"), JSON.stringify(manifest, null, 2), "utf8");
    if (fs.existsSync(permanent)) await fs.promises.rename(permanent, previous);
    await fs.promises.rename(candidate, permanent);
    await fs.promises.rm(previous, { recursive: true, force: true });
    return permanent;
  } catch (error) {
    await fs.promises.rm(candidate, { recursive: true, force: true }).catch(() => {});
    if (!fs.existsSync(permanent) && fs.existsSync(previous)) await fs.promises.rename(previous, permanent).catch(() => {});
    throw error;
  }
}

function readProfileSnapshotManifest(profileId) {
  try { return JSON.parse(fs.readFileSync(path.join(P.clientProfile(profileId), "manifest.json"), "utf8")); }
  catch { return null; }
}

async function stageCachedChange(profileId, stagingRoot, change, revision) {
  const cachedManifest = readProfileSnapshotManifest(profileId);
  if (!cachedManifest || String(cachedManifest.revision || "") !== String(revision || "")) return null;
  const source = safeLocal(P.clientProfile(profileId), change.target);
  try {
    const stat = await fs.promises.stat(source);
    if (!stat.isFile() || stat.size !== change.size || await sha256File(source) !== change.sha256) return null;
  } catch { return null; }
  const local = safeLocal(stagingRoot, change.target);
  await fs.promises.mkdir(path.dirname(local), { recursive: true });
  const temp = `${local}.rsdw-sync-${crypto.randomBytes(6).toString("hex")}`;
  await fs.promises.copyFile(source, temp);
  return { ...change, local, temp, cached: true };
}

function pruneRecovery(profileId, keep = 5) {
  const root = path.join(P.data(), "sync-recovery", safeProfileSegment(profileId));
  let entries = [];
  try { entries = fs.readdirSync(root, { withFileTypes: true }).filter((entry) => entry.isDirectory()).map((entry) => entry.name).sort().reverse(); }
  catch { return; }
  for (const stale of entries.slice(keep)) {
    try { fs.rmSync(path.join(root, stale), { recursive: true, force: true }); } catch {}
  }
}

async function sameProjection(source, destination) {
  try {
    const [sourceStat, destinationStat] = await Promise.all([fs.promises.stat(source), fs.promises.stat(destination)]);
    if (sourceStat.dev === destinationStat.dev && sourceStat.ino === destinationStat.ino) return true;
    const linkStat = await fs.promises.lstat(destination);
    if (linkStat.isSymbolicLink()) return path.resolve(await fs.promises.realpath(destination)) === path.resolve(source);
  } catch {}
  return false;
}

async function projectProfileFile(source, destination) {
  await fs.promises.mkdir(path.dirname(destination), { recursive: true });
  try {
    await fs.promises.link(source, destination);
    return "hardlink";
  } catch {
    try {
      await fs.promises.symlink(source, destination, "file");
      return "symlink";
    } catch {
      await fs.promises.copyFile(source, destination);
      return "copy";
    }
  }
}

async function activateProfileSnapshot(profileId, options = {}) {
  const profile = options.profile || dbm.getProfile(profileId);
  if (!profile) throw new Error("World profile not found");
  const connection = JSON.parse(profile.connection_json || "{}");
  const service = options.service || (["steam", "epic", "gamepass"].includes(connection.service) ? connection.service : (connection.platform === "gamepass" ? "gamepass" : "steam"));
  const install = steamlib.normalizeGameInstall(options.install || profile.client_install || dbm.getSetting(`clientInstall:${service}`, null));
  if (!install) throw new Error(`This World needs a ${steamlib.serviceLabel(service)} game installation before its mod profile can be activated.`);
  const snapshot = P.clientProfile(profileId);
  const manifest = options.manifest || readProfileSnapshotManifest(profileId);
  if (!manifest) throw new Error("Synchronize this World before activating its mod profile");
  const files = (manifest.units || []).flatMap((unit) => unit.files || []);
  const declared = new Set(files.map((file) => String(file.target)));
  const declaredKeys = new Set([...declared].map(targetKey));
  const activeLedger = dbm.getSetting(activeLedgerKey(service, install), dbm.getSetting(`clientActiveSync:${service}`, { files: [] }));
  const recoveryRoot = options.recoveryRoot || path.join(P.data(), "sync-recovery", safeProfileSegment(profileId), `activate-${new Date().toISOString().replace(/[:.]/g, "-")}-${crypto.randomBytes(4).toString("hex")}`);
  const onProgress = options.onProgress || (() => {});
  const operations = [];
  const deployment = { hardlink: 0, symlink: 0, copy: 0, unchanged: 0, removed: 0 };

  for (const target of activeLedger?.files || []) {
    if (!declaredKeys.has(targetKey(target))) operations.push({ action: "remove", target, destination: safeLocal(install, target), backup: null });
  }
  for (const file of files) {
    const source = safeLocal(snapshot, file.target);
    const destination = safeLocal(install, file.target);
    if (!fs.existsSync(source)) throw new Error(`World profile cache is missing ${file.target}; synchronize it again`);
    const activeCopy = activeLedger?.profileId === profileId && String(activeLedger?.revision || "") === String(manifest.revision || "");
    let unchangedCopy = false;
    if (activeCopy && fs.existsSync(destination)) {
      try {
        const stat = await fs.promises.stat(destination);
        unchangedCopy = stat.isFile() && stat.size === Number(file.size) && await sha256File(destination) === file.sha256;
      } catch {}
    }
    if (await sameProjection(source, destination) || unchangedCopy) { deployment.unchanged++; continue; }
    operations.push({ action: "project", target: file.target, source, destination, backup: null });
  }

  const applied = [];
  try {
    for (let index = 0; index < operations.length; index++) {
      const operation = operations[index];
      if (fs.existsSync(operation.destination)) {
        const stat = await fs.promises.lstat(operation.destination);
        if (stat.isDirectory()) throw new Error(`Cannot activate ${operation.target}: a directory occupies the managed file path`);
        operation.backup = backupPath(recoveryRoot, operation.target);
        await fs.promises.mkdir(path.dirname(operation.backup), { recursive: true });
        await fs.promises.copyFile(operation.destination, operation.backup);
        await fs.promises.rm(operation.destination, { force: true });
      }
      if (operation.action === "project") {
        operation.deployment = await projectProfileFile(operation.source, operation.destination);
        deployment[operation.deployment]++;
      } else deployment.removed++;
      applied.push(operation);
      onProgress({ phase: "install", percent: Math.round(80 + ((index + 1) / Math.max(1, operations.length)) * 18), message: "Activating World mod profile…", line: `${operation.action === "project" ? `Projected (${operation.deployment})` : "Removed retired file"} ${operation.target}` });
    }
  } catch (error) {
    for (const operation of [...applied].reverse()) {
      try {
        await fs.promises.rm(operation.destination, { force: true });
        if (operation.backup && fs.existsSync(operation.backup)) {
          await fs.promises.mkdir(path.dirname(operation.destination), { recursive: true });
          await fs.promises.copyFile(operation.backup, operation.destination);
        }
      } catch {}
    }
    throw error;
  }

  const activatedAt = Date.now();
  dbm.setSetting(activeLedgerKey(service, install), { profileId, worldId: manifest.world?.id || profile.server_world_id, revision: manifest.revision, files: [...declared], syncedAt: activatedAt });
  dbm.upsertProfile({
    profile_id: profileId,
    connection: {
      ...connection,
      modDeployment: {
        mode: deployment.copy ? "linked-with-copy-fallback" : "linked",
        ...deployment,
        profilePath: snapshot,
        installPath: install,
        activatedAt,
      },
    },
  });
  if (!options.recoveryRoot) pruneRecovery(profileId);
  const saves = profileSaves.activateForProfile(profileId);
  return { profileId, service, install, snapshot, revision: manifest.revision, deployment, saves, changed: operations.length };
}

async function performSync(profileId, onProgress = () => {}) {
  const profile = dbm.getProfile(profileId);
  if (!profile) throw new Error("World profile not found");
  const connection = JSON.parse(profile.connection_json || "{}");
  const address = String(connection.address || connection.internalIp || connection.externalIp || "").trim();
  const worldId = String(connection.worldId || profile.server_world_id || "").trim();
  const port = Number(connection.syncPort || 4318);
  const service = ["steam", "epic", "gamepass"].includes(connection.service) ? connection.service : (connection.platform === "gamepass" ? "gamepass" : "steam");
  const platform = service === "gamepass" ? "gamepass" : "steam";
  const install = steamlib.normalizeGameInstall(profile.client_install || dbm.getSetting(`clientInstall:${service}`, null));
  if (!address || !worldId || !Number.isInteger(port) || port < 1 || port > 65535) throw new Error("This World needs a valid Sync endpoint");
  if (!install) throw new Error(`This World needs a ${steamlib.serviceLabel(service)} game installation. Choose it on the World page or under Application Setup.`);
  const base = `http://${address}:${port}/api/sync/public/${encodeURIComponent(worldId)}`;
  onProgress({ phase: "prepare", percent: 1, message: "Downloading World manifest…", line: `Connecting to ${address}:${port}…` });
  let manifest;
  try { manifest = await fetchJson(base, connection.password, platform); }
  catch (error) {
    manifest = readProfileSnapshotManifest(profileId);
    if (!manifest) throw error;
    onProgress({ phase: "prepare", percent: 2, message: "Using saved World profile…", line: `Host unavailable; using authenticated cached manifest ${manifest.revision}.` });
  }
  const stagingRoot = await fs.promises.mkdtemp(path.join(P.staging(), `client-${safeProfileSegment(profileId)}-`));
  const comparison = manifestLib.compareManifest(manifest, install);
  onProgress({ phase: "prepare", percent: 4, message: "Preparing managed downloads…", line: `Manifest ${manifest.revision}: ${comparison.changes.length} file(s) to synchronize.` });
  const declared = new Set((manifest.units || []).flatMap((unit) => unit.files || []).map((file) => String(file.target)));
  const declaredKeys = new Set([...declared].map(targetKey));
  const oldLedger = dbm.getSetting(ledgerKey(profileId), { files: [] });
  const activeLedger = dbm.getSetting(activeLedgerKey(service, install), dbm.getSetting(`clientActiveSync:${service}`, { files: [] }));
  const removals = [];

  const previouslyManaged = new Set([...(activeLedger?.files || []), ...(activeLedger?.profileId ? [] : (oldLedger?.files || []))]);
  for (const target of previouslyManaged) {
    if (declaredKeys.has(targetKey(target))) continue;
    const local = safeLocal(install, target);
    if (fs.existsSync(local) && fs.statSync(local).isFile()) removals.push({ target, local });
  }

  // Download and verify everything before changing a live game file. Three
  // concurrent streams keep sync quick without saturating a friend's host.
  let staged = [];
  const downloadBytes = comparison.changes.reduce((sum, change) => sum + Number(change.size || 0), 0);
  let receivedBytes = 0;
  try {
    await mapLimit(comparison.changes, 3, async (change) => {
      const cached = await stageCachedChange(profileId, stagingRoot, change, manifest.revision);
      if (cached) {
        receivedBytes += Number(change.size || 0);
        staged.push(cached);
        onProgress({ phase: "download", percent: downloadBytes ? Math.round(5 + receivedBytes / downloadBytes * 72) : 77, message: `Restoring ${change.unitName || "managed mod"}…`, line: `Restored ${change.target} from this World profile cache.` });
        return cached;
      }
      onProgress({ phase: "download", percent: downloadBytes ? Math.round(5 + receivedBytes / downloadBytes * 72) : 77, message: `Downloading ${change.unitName || "managed mod"}…`, line: `Downloading ${change.target} (${change.size} bytes)…` });
      const item = await downloadChange(base, connection, platform, stagingRoot, change, (bytes) => {
        receivedBytes += bytes;
        onProgress({ phase: "download", percent: downloadBytes ? Math.round(5 + receivedBytes / downloadBytes * 72) : 77, message: `Downloading ${change.unitName || "managed mod"}…` });
      });
      staged.push(item);
      onProgress({ phase: "verify", percent: downloadBytes ? Math.round(5 + receivedBytes / downloadBytes * 72) : 77, message: `Verified ${change.unitName || "managed mod"}`, line: `Verified ${change.target}` });
      return item;
    });
  } catch (error) {
    await Promise.all(staged.map((item) => fs.promises.rm(item.temp, { force: true }).catch(() => {})));
    await fs.promises.rm(stagingRoot, { recursive: true, force: true }).catch(() => {});
    throw error;
  }

  onProgress({ phase: "verify", percent: 78, message: "Saving World profile snapshot…", line: "Saving the complete verified mod set into this World profile." });
  let snapshot;
  try { snapshot = await saveProfileSnapshot(profileId, manifest, install, staged); }
  catch (error) {
    await Promise.all(staged.map((item) => fs.promises.rm(item.temp, { force: true }).catch(() => {})));
    await fs.promises.rm(stagingRoot, { recursive: true, force: true }).catch(() => {});
    throw error;
  }

  const receiptId = `${new Date().toISOString().replace(/[:.]/g, "-")}-${crypto.randomBytes(4).toString("hex")}`;
  const recoveryRoot = path.join(P.data(), "sync-recovery", safeProfileSegment(profileId), receiptId);
  let activation;
  try {
    activation = await activateProfileSnapshot(profileId, { profile, manifest, install, service, recoveryRoot, onProgress });
    writeReceipt(recoveryRoot, { schema: "RSDWSync.ClientReceipt.v2", profileId, worldId, revision: manifest.revision, status: "complete", createdAt: new Date().toISOString(), completedAt: new Date().toISOString(), deployment: activation.deployment });
  } catch (error) {
    throw error;
  } finally {
    await Promise.all(staged.map((item) => fs.promises.rm(item.temp, { force: true }).catch(() => {})));
    await fs.promises.rm(stagingRoot, { recursive: true, force: true }).catch(() => {});
  }

  const syncedAt = Date.now();
  dbm.setSetting(ledgerKey(profileId), { worldId, revision: manifest.revision, files: [...declared], syncedAt, receipt: path.join(recoveryRoot, "receipt.json"), snapshot });
  const identity = manifest.world?.identity || {};
  dbm.upsertProfile({
    profile_id: profileId,
    display_name: manifest.world?.name || profile.display_name,
    connection: {
      ...connection,
      worldIdentity: {
        iconData: identity.iconData || null,
        bannerData: identity.bannerData || null,
        accentColor: identity.accentColor || null,
      },
      worldType: manifest.world?.type || connection.worldType || "Private",
      rules: manifest.world?.rules || connection.rules || {},
      modBadges: [...new Set((manifest.units || []).map((unit) => String(unit.type || "mod").toUpperCase()))],
      modCount: (manifest.units || []).length,
      cachedModProfile: { revision: manifest.revision, files: declared.size, savedAt: syncedAt },
      manifestUpdate: { available: false, remoteRevision: manifest.revision, checkedAt: syncedAt },
      modDeployment: {
        mode: activation.deployment.copy ? "linked-with-copy-fallback" : "linked",
        ...activation.deployment,
        profilePath: snapshot,
        installPath: install,
        activatedAt: syncedAt,
      },
    },
    last_manifest_revision: manifest.revision,
  });
  pruneRecovery(profileId);
  onProgress({ phase: "finalizing", percent: 100, message: "World synchronized", line: `Synchronization complete: ${staged.length} downloaded, ${activation.deployment.hardlink + activation.deployment.symlink} linked, ${activation.deployment.copy} copied as fallback; ${declared.size} profile files cached.` });
  return { manifest, installed: staged.map((item) => item.target), removed: removals.map((item) => item.target), current: staged.length === 0 && activation.changed === 0, receipt: path.join(recoveryRoot, "receipt.json"), snapshot, deployment: activation.deployment };
}

function synchronizeProfile(profileId, onProgress = () => {}) {
  const key = String(profileId || "");
  if (inFlight.has(key)) return inFlight.get(key);
  const run = syncQueue.catch(() => {}).then(() => performSync(key, onProgress));
  syncQueue = run.catch(() => {});
  inFlight.set(key, run);
  run.then(
    () => { if (inFlight.get(key) === run) inFlight.delete(key); },
    () => { if (inFlight.get(key) === run) inFlight.delete(key); },
  );
  return run;
}

module.exports = { synchronizeProfile, activateProfileSnapshot, safeLocal };
