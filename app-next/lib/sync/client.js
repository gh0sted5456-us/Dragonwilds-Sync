const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { Readable, Transform } = require("stream");
const { pipeline } = require("stream/promises");
const dbm = require("../db");
const manifestLib = require("./manifest");
const steamlib = require("../steamlibrary");
const { P } = require("../paths");

const ledgerKey = (profileId) => `clientSyncLedger:${profileId}`;
const activeLedgerKey = (platform) => `clientActiveSync:${platform}`;
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

async function downloadChange(base, connection, platform, install, change, onBytes = () => {}) {
  const local = safeLocal(install, change.target);
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
    const response = await fetch(downloadUrl, {
      cache: "no-store",
      signal: controller.signal,
      headers: { "X-RSDW-World-Password": String(connection.password || ""), "X-RSDW-Client-Platform": platform },
    });
    if (!response.ok || !response.body) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || `Could not download ${change.target} (${response.status})`);
    }
    const contentLengthHeader = response.headers.get("content-length");
    const contentLength = contentLengthHeader == null ? null : Number(contentLengthHeader);
    if (contentLength !== null && Number.isFinite(contentLength) && contentLength !== change.size) throw new Error(`Size declaration changed while downloading ${change.target}`);
    const meter = new Transform({ transform(chunk, _encoding, callback) { onBytes(chunk.length); callback(null, chunk); } });
    await pipeline(Readable.fromWeb(response.body), meter, fs.createWriteStream(temp, { flags: "wx" }));
    const stat = await fs.promises.stat(temp);
    if (stat.size !== change.size) throw new Error(`Size verification failed for ${change.target}`);
    if (await sha256File(temp) !== change.sha256) throw new Error(`Hash verification failed for ${change.target}`);
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

async function stageCachedChange(profileId, install, change, revision) {
  const cachedManifest = readProfileSnapshotManifest(profileId);
  if (!cachedManifest || String(cachedManifest.revision || "") !== String(revision || "")) return null;
  const source = safeLocal(P.clientProfile(profileId), change.target);
  try {
    const stat = await fs.promises.stat(source);
    if (!stat.isFile() || stat.size !== change.size || await sha256File(source) !== change.sha256) return null;
  } catch { return null; }
  const local = safeLocal(install, change.target);
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

async function performSync(profileId, onProgress = () => {}) {
  const profile = dbm.getProfile(profileId);
  if (!profile) throw new Error("World profile not found");
  const connection = JSON.parse(profile.connection_json || "{}");
  const address = String(connection.address || connection.internalIp || connection.externalIp || "").trim();
  const worldId = String(connection.worldId || profile.server_world_id || "").trim();
  const port = Number(connection.syncPort || 4318);
  const platform = connection.platform === "gamepass" ? "gamepass" : "steam";
  const install = steamlib.normalizeGameInstall(dbm.getSetting(`clientInstall:${platform}`, null));
  if (!address || !worldId || !Number.isInteger(port) || port < 1 || port > 65535) throw new Error("This World needs a valid Sync endpoint");
  if (!install) throw new Error(`Application Setup -> Play -> ${platform === "gamepass" ? "PC Game Pass" : "Steam"} is not configured.`);
  const base = `http://${address}:${port}/api/sync/public/${encodeURIComponent(worldId)}`;
  onProgress({ phase: "prepare", percent: 1, message: "Downloading World manifest…", line: `Connecting to ${address}:${port}…` });
  let manifest;
  try { manifest = await fetchJson(base, connection.password, platform); }
  catch (error) {
    manifest = readProfileSnapshotManifest(profileId);
    if (!manifest) throw error;
    onProgress({ phase: "prepare", percent: 2, message: "Using saved World profile…", line: `Host unavailable; using authenticated cached manifest ${manifest.revision}.` });
  }
  const comparison = manifestLib.compareManifest(manifest, install);
  onProgress({ phase: "prepare", percent: 4, message: "Preparing managed downloads…", line: `Manifest ${manifest.revision}: ${comparison.changes.length} file(s) to synchronize.` });
  const declared = new Set((manifest.units || []).flatMap((unit) => unit.files || []).map((file) => String(file.target)));
  const declaredKeys = new Set([...declared].map(targetKey));
  const oldLedger = dbm.getSetting(ledgerKey(profileId), { files: [] });
  const activeLedger = dbm.getSetting(activeLedgerKey(platform), { files: [] });
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
      const cached = await stageCachedChange(profileId, install, change, manifest.revision);
      if (cached) {
        receivedBytes += Number(change.size || 0);
        staged.push(cached);
        onProgress({ phase: "download", percent: downloadBytes ? Math.round(5 + receivedBytes / downloadBytes * 72) : 77, message: `Restoring ${change.unitName || "managed mod"}…`, line: `Restored ${change.target} from this World profile cache.` });
        return cached;
      }
      onProgress({ phase: "download", percent: downloadBytes ? Math.round(5 + receivedBytes / downloadBytes * 72) : 77, message: `Downloading ${change.unitName || "managed mod"}…`, line: `Downloading ${change.target} (${change.size} bytes)…` });
      const item = await downloadChange(base, connection, platform, install, change, (bytes) => {
        receivedBytes += bytes;
        onProgress({ phase: "download", percent: downloadBytes ? Math.round(5 + receivedBytes / downloadBytes * 72) : 77, message: `Downloading ${change.unitName || "managed mod"}…` });
      });
      staged.push(item);
      onProgress({ phase: "verify", percent: downloadBytes ? Math.round(5 + receivedBytes / downloadBytes * 72) : 77, message: `Verified ${change.unitName || "managed mod"}`, line: `Verified ${change.target}` });
      return item;
    });
  } catch (error) {
    await Promise.all(staged.map((item) => fs.promises.rm(item.temp, { force: true }).catch(() => {})));
    throw error;
  }

  onProgress({ phase: "verify", percent: 78, message: "Saving World profile snapshot…", line: "Saving the complete verified mod set into this World profile." });
  let snapshot;
  try { snapshot = await saveProfileSnapshot(profileId, manifest, install, staged); }
  catch (error) {
    await Promise.all(staged.map((item) => fs.promises.rm(item.temp, { force: true }).catch(() => {})));
    throw error;
  }

  const receiptId = `${new Date().toISOString().replace(/[:.]/g, "-")}-${crypto.randomBytes(4).toString("hex")}`;
  const recoveryRoot = path.join(P.data(), "sync-recovery", safeProfileSegment(profileId), receiptId);
  const operations = [
    ...staged.map((item) => ({ action: item.state === "changed" ? "replace" : "install", target: item.target, local: item.local, backup: null })),
    ...removals.map((item) => ({ action: "remove", target: item.target, local: item.local, backup: null })),
  ];
  const receipt = { schema: "RSDWSync.ClientReceipt.v1", profileId, worldId, revision: manifest.revision, status: "applying", createdAt: new Date().toISOString(), operations };
  onProgress({ phase: "install", percent: 80, message: "Installing verified mod files…", line: "All downloads verified; applying the synchronized files atomically." });
  try { writeReceipt(recoveryRoot, receipt); }
  catch (error) {
    await Promise.all(staged.map((item) => fs.promises.rm(item.temp, { force: true }).catch(() => {})));
    throw error;
  }

  const applied = [];
  try {
    for (let i = 0; i < staged.length; i++) {
      const item = staged[i], operation = operations[i];
      if (fs.existsSync(item.local)) {
        operation.backup = backupPath(recoveryRoot, item.target);
        await fs.promises.mkdir(path.dirname(operation.backup), { recursive: true });
        await fs.promises.copyFile(item.local, operation.backup);
        await fs.promises.rm(item.local, { force: true });
      }
      await fs.promises.rename(item.temp, item.local);
      applied.push(operation);
      writeReceipt(recoveryRoot, receipt);
      onProgress({ phase: "install", percent: Math.round(80 + ((i + 1) / Math.max(1, staged.length + removals.length)) * 18), message: "Installing verified mod files…", line: `Installed ${item.target}` });
    }
    for (let i = 0; i < removals.length; i++) {
      const item = removals[i], operation = operations[staged.length + i];
      operation.backup = backupPath(recoveryRoot, item.target);
      await fs.promises.mkdir(path.dirname(operation.backup), { recursive: true });
      await fs.promises.copyFile(item.local, operation.backup);
      await fs.promises.rm(item.local, { force: true });
      applied.push(operation);
      writeReceipt(recoveryRoot, receipt);
      onProgress({ phase: "install", percent: Math.round(80 + ((staged.length + i + 1) / Math.max(1, staged.length + removals.length)) * 18), message: "Removing retired managed files…", line: `Removed retired managed file ${item.target}` });
    }
    receipt.status = "complete";
    receipt.completedAt = new Date().toISOString();
    writeReceipt(recoveryRoot, receipt);
  } catch (error) {
    for (const operation of [...applied].reverse()) {
      try {
        if (operation.backup && fs.existsSync(operation.backup)) {
          await fs.promises.mkdir(path.dirname(operation.local), { recursive: true });
          await fs.promises.copyFile(operation.backup, operation.local);
        } else await fs.promises.rm(operation.local, { force: true });
      } catch {}
    }
    receipt.status = "rolled-back";
    receipt.error = error.message;
    receipt.completedAt = new Date().toISOString();
    writeReceipt(recoveryRoot, receipt);
    throw error;
  } finally {
    await Promise.all(staged.map((item) => fs.promises.rm(item.temp, { force: true }).catch(() => {})));
  }

  const syncedAt = Date.now();
  dbm.setSetting(ledgerKey(profileId), { worldId, revision: manifest.revision, files: [...declared], syncedAt, receipt: path.join(recoveryRoot, "receipt.json"), snapshot });
  dbm.setSetting(activeLedgerKey(platform), { profileId, worldId, revision: manifest.revision, files: [...declared], syncedAt });
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
    },
    last_manifest_revision: manifest.revision,
  });
  pruneRecovery(profileId);
  onProgress({ phase: "finalizing", percent: 100, message: "World synchronized", line: `Synchronization complete: ${staged.length} installed, ${removals.length} removed; ${declared.size} profile files cached.` });
  return { manifest, installed: staged.map((item) => item.target), removed: removals.map((item) => item.target), current: staged.length === 0 && removals.length === 0, receipt: path.join(recoveryRoot, "receipt.json"), snapshot };
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

module.exports = { synchronizeProfile, safeLocal };
