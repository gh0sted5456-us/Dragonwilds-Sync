const dbm = require("../db");

function targetFor(profile) {
  const connection = JSON.parse(profile.connection_json || "{}");
  if (connection.localWorld) return null;
  const address = String(connection.address || connection.internalIp || connection.externalIp || "").trim();
  const worldId = String(connection.worldId || profile.server_world_id || "").trim();
  const port = Number(connection.syncPort || 4318);
  if (!address || !worldId || !Number.isInteger(port) || port < 1 || port > 65535) throw new Error("This World does not have a complete Sync endpoint");
  const host = address.includes(":") && !address.startsWith("[") ? `[${address}]` : address;
  return { connection, address, worldId, port, url: `http://${host}:${port}/api/sync/public/${encodeURIComponent(worldId)}` };
}

async function refreshProfile(profile, options = {}) {
  const target = targetFor(profile);
  if (!target) return { profileId: profile.profile_id, skipped: true, reason: "local" };
  const timeoutMs = Math.min(Math.max(Number(options.timeoutMs || 8000), 1000), 15000);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const service = target.connection.service === "gamepass" || target.connection.platform === "gamepass" ? "gamepass" : "steam";
  let response;
  try {
    response = await (options.fetchImpl || fetch)(target.url, {
      cache: "no-store",
      signal: controller.signal,
      headers: {
        "X-RSDW-World-Password": String(target.connection.password || ""),
        "X-RSDW-Client-Platform": service,
      },
    });
  } finally { clearTimeout(timer); }
  let payload = {};
  try { payload = await response.json(); } catch {}
  if (!response.ok || !payload.manifest?.revision) throw new Error(payload.error || `World manifest request failed (${response.status})`);
  const manifest = payload.manifest;
  const previousRevision = String(profile.last_manifest_revision || "");
  const remoteRevision = String(manifest.revision);
  const cachedRevision = String(target.connection.cachedModProfile?.revision || "");
  const changed = !!previousRevision && previousRevision !== remoteRevision;
  const updateAvailable = cachedRevision
    ? cachedRevision !== remoteRevision
    : Boolean(target.connection.manifestUpdate?.available || changed);
  const identity = manifest.world?.identity || {};
  const nextConnection = {
    ...target.connection,
    worldIdentity: {
      iconData: identity.iconData || null,
      bannerData: identity.bannerData || null,
      accentColor: identity.accentColor || null,
    },
    worldType: manifest.world?.type || target.connection.worldType || "Private",
    rules: manifest.world?.rules || target.connection.rules || {},
    modBadges: [...new Set((manifest.units || []).map((unit) => String(unit.type || "mod").toUpperCase()))],
    modCount: (manifest.units || []).length,
    hostingType: manifest.transport?.hostingType || target.connection.hostingType || "local",
    deliveryMode: manifest.transport?.storageMode || target.connection.deliveryMode || "local",
    deliveryProvider: manifest.transport?.storageProvider || target.connection.deliveryProvider || "local",
    manifestUpdate: { available: updateAvailable, remoteRevision, checkedAt: Date.now() },
  };
  const updated = dbm.upsertProfile({
    profile_id: profile.profile_id,
    display_name: manifest.world?.name || profile.display_name,
    connection: nextConnection,
    last_manifest_revision: remoteRevision,
  });
  return { profileId: profile.profile_id, changed, updateAvailable, revision: remoteRevision, profile: updated };
}

module.exports = { targetFor, refreshProfile };
