const dbm = require("../db");
const steamlib = require("../steamlibrary");
const syncManifest = require("./manifest");

async function requestJson(url, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(url, { ...options, cache: "no-store", redirect: "error", signal: controller.signal });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Host request failed (${response.status})`);
    return payload;
  } finally { clearTimeout(timeout); }
}

async function requestClientAdmission(profileId, { expectedRevision } = {}) {
  const profile = dbm.getProfile(profileId);
  if (!profile) throw new Error("World profile not found");
  const connection = JSON.parse(profile.connection_json || "{}");
  dbm.upsertProfile({ profile_id: profileId, connection: { ...connection, admission: null } });
  const address = String(connection.address || connection.internalIp || connection.externalIp || "").trim();
  const worldId = String(connection.worldId || profile.server_world_id || "").trim();
  const port = Number(connection.syncPort || 4318);
  const service = ["steam", "epic", "gamepass"].includes(connection.service) ? connection.service : connection.platform === "gamepass" ? "gamepass" : "steam";
  const platform = service === "gamepass" ? "gamepass" : "steam";
  const install = steamlib.normalizeGameInstall(profile.client_install || dbm.getSetting(`clientInstall:${service}`, null));
  if (!address || !worldId || !install || !Number.isInteger(port) || port < 1 || port > 65535) throw new Error("This World profile is missing its Sync endpoint or game installation");
  if (worldId.startsWith("profile-")) return null; // Shares distribute files, not login approval.
  const base = `http://${address}:${port}/api/sync/public/${encodeURIComponent(worldId)}`;
  const headers = { "Content-Type": "application/json", "X-RSDW-World-Password": String(connection.password || ""), "X-RSDW-Client-Platform": platform };
  const { manifest } = await requestJson(base, { headers });
  if (!manifest || manifest.protocol !== syncManifest.PROTOCOL || manifest.protocolVersion !== syncManifest.PROTOCOL_VERSION || manifest.world?.id !== worldId) throw new Error("The host returned an incompatible admission manifest");
  if (expectedRevision && manifest.revision !== expectedRevision) throw new Error("The host's manifest changed during sync. Check for changes and sync again.");
  const attestation = syncManifest.createClientAttestation(manifest, install);
  const payload = await requestJson(`${base}/admission`, { method: "POST", headers, body: JSON.stringify(attestation) });
  if (!payload.admission?.approved || payload.admission.revision !== manifest.revision) throw new Error("The host did not approve this client manifest");
  const { token: _token, ...savedAdmission } = payload.admission;
  const latest = JSON.parse(dbm.getProfile(profileId).connection_json || "{}");
  dbm.upsertProfile({ profile_id: profileId, connection: { ...latest, admission: savedAdmission } });
  return payload.admission;
}
module.exports = { requestClientAdmission };
