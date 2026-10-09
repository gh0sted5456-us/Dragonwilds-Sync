const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { Readable } = require("stream");
const { pipeline } = require("stream/promises");
const dbm = require("../db");
const manifestLib = require("./manifest");
const steamlib = require("../steamlibrary");
const { P } = require("../paths");

const ledgerKey = (profileId) => `clientSyncLedger:${profileId}`;
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

async function downloadChange(base, connection, platform, install, change) {
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
    await pipeline(Readable.fromWeb(response.body), fs.createWriteStream(temp, { flags: "wx" }));
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

function pruneRecovery(profileId, keep = 5) {
  const root = path.join(P.data(), "sync-recovery", safeProfileSegment(profileId));
  let entries = [];
  try { entries = fs.readdirSync(root, { withFileTypes: true }).filter((entry) => entry.isDirectory()).map((entry) => entry.name).sort().reverse(); }
  catch { return; }
  for (const stale of entries.slice(keep)) {
    try { fs.rmSync(path.join(root, stale), { recursive: true, force: true }); } catch {}
  }
}

async function performSync(profileId) {
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
  const manifest = await fetchJson(base, connection.password, platform);
  const comparison = manifestLib.compareManifest(manifest, install);
  const declared = new Set((manifest.units || []).flatMap((unit) => unit.files || []).map((file) => String(file.target)));
  const declaredKeys = new Set([...declared].map(targetKey));
  const oldLedger = dbm.getSetting(ledgerKey(profileId), { files: [] });
  const removals = [];

  for (const target of oldLedger?.files || []) {
    if (declaredKeys.has(targetKey(target))) continue;
    const local = safeLocal(install, target);
    if (fs.existsSync(local) && fs.statSync(local).isFile()) removals.push({ target, local });
  }

  // Download and verify everything before changing a live game file. Three
  // concurrent streams keep sync quick without saturating a friend's host.
  let staged = [];
  try {
    await mapLimit(comparison.changes, 3, async (change) => {
      const item = await downloadChange(base, connection, platform, install, change);
      staged.push(item);
      return item;
    });
  } catch (error) {
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
    }
    for (let i = 0; i < removals.length; i++) {
      const item = removals[i], operation = operations[staged.length + i];
      operation.backup = backupPath(recoveryRoot, item.target);
      await fs.promises.mkdir(path.dirname(operation.backup), { recursive: true });
      await fs.promises.copyFile(item.local, operation.backup);
      await fs.promises.rm(item.local, { force: true });
      applied.push(operation);
      writeReceipt(recoveryRoot, receipt);
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

  dbm.setSetting(ledgerKey(profileId), { worldId, revision: manifest.revision, files: [...declared], syncedAt: Date.now(), receipt: path.join(recoveryRoot, "receipt.json") });
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
    },
    last_manifest_revision: manifest.revision,
  });
  pruneRecovery(profileId);
  return { manifest, installed: staged.map((item) => item.target), removed: removals.map((item) => item.target), current: staged.length === 0 && removals.length === 0, receipt: path.join(recoveryRoot, "receipt.json") };
}

function synchronizeProfile(profileId) {
  const key = String(profileId || "");
  if (inFlight.has(key)) return inFlight.get(key);
  const run = syncQueue.catch(() => {}).then(() => performSync(key));
  syncQueue = run.catch(() => {});
  inFlight.set(key, run);
  run.then(
    () => { if (inFlight.get(key) === run) inFlight.delete(key); },
    () => { if (inFlight.get(key) === run) inFlight.delete(key); },
  );
  return run;
}

module.exports = { synchronizeProfile, safeLocal };
