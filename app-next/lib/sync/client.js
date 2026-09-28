const fs = require("fs");
const path = require("path");
const dbm = require("../db");
const manifestLib = require("./manifest");
const steamlib = require("../steamlibrary");

const ledgerKey = (profileId) => `clientSyncLedger:${profileId}`;

function safeLocal(install, target) {
  const relative = String(target || "").replace(/\\/g, "/");
  if (!relative.startsWith("RSDragonwilds/") || relative.split("/").some((part) => !part || part === "." || part === "..")) throw new Error("World manifest contains an unsafe mod path");
  const root = path.resolve(install) + path.sep;
  const local = path.resolve(install, ...relative.split("/"));
  if (!local.toLowerCase().startsWith(root.toLowerCase())) throw new Error("World manifest path escapes the game installation");
  return local;
}

async function fetchJson(url, password, platform) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(url, { cache: "no-store", signal: controller.signal, headers: { "X-RSDW-World-Password": String(password || ""), "X-RSDW-Client-Platform": platform === "gamepass" ? "gamepass" : "steam" } });
    const data = await response.json();
    if (!response.ok || !data.manifest) throw new Error(data.error || "World did not return a mod manifest");
    return data.manifest;
  } finally { clearTimeout(timeout); }
}

async function synchronizeProfile(profileId) {
  const profile = dbm.getProfile(profileId);
  if (!profile) throw new Error("World profile not found");
  const connection = JSON.parse(profile.connection_json || "{}");
  const address = String(connection.address || connection.internalIp || connection.externalIp || "").trim();
  const worldId = String(connection.worldId || profile.server_world_id || "").trim();
  const port = Number(connection.syncPort || 4317);
  const platform = connection.platform === "gamepass" ? "gamepass" : "steam";
  const install = steamlib.normalizeGameInstall(platform === "gamepass" ? connection.gamepassInstall : connection.steamInstall) || steamlib.normalizeGameInstall(profile.client_install);
  if (!address || !worldId || !install) throw new Error("This World needs a valid endpoint and Dragonwilds installation");
  const base = `http://${address}:${port}/api/sync/public/${encodeURIComponent(worldId)}`;
  const manifest = await fetchJson(base, connection.password, platform);
  const comparison = manifestLib.compareManifest(manifest, install);
  const declared = new Set((manifest.units || []).flatMap((unit) => unit.files || []).map((file) => file.target));
  const oldLedger = dbm.getSetting(ledgerKey(profileId), { files: [] });
  const removed = [];

  // Only remove paths previously installed by this profile. Unrelated user mods are sacred.
  for (const target of oldLedger?.files || []) {
    if (declared.has(target)) continue;
    const local = safeLocal(install, target);
    if (fs.existsSync(local) && fs.statSync(local).isFile()) { fs.unlinkSync(local); removed.push(target); }
  }

  const installed = [];
  for (const change of comparison.changes) {
    const local = safeLocal(install, change.target);
    fs.mkdirSync(path.dirname(local), { recursive: true });
    const response = await fetch(`${base}/file?target=${encodeURIComponent(change.target)}`, { cache: "no-store", headers: { "X-RSDW-World-Password": String(connection.password || ""), "X-RSDW-Client-Platform": platform } });
    if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(data.error || `Could not download ${change.target}`); }
    const temp = `${local}.rsdw-sync-download`;
    fs.writeFileSync(temp, Buffer.from(await response.arrayBuffer()));
    if (manifestLib.sha256File(temp) !== change.sha256) { fs.rmSync(temp, { force: true }); throw new Error(`Hash verification failed for ${change.target}`); }
    fs.renameSync(temp, local);
    installed.push(change.target);
  }

  dbm.setSetting(ledgerKey(profileId), { worldId, revision: manifest.revision, files: [...declared], syncedAt: Date.now() });
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
    },
    last_manifest_revision: manifest.revision,
  });
  return { manifest, installed, removed, current: installed.length === 0 && removed.length === 0 };
}

module.exports = { synchronizeProfile };
