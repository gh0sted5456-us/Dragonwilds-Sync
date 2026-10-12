import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const steamlib = require("@/lib/steamlibrary");
const syncManifest = require("@/lib/sync/manifest");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(_req, { params }) {
  try {
    const profile = dbm.getProfile(params.id);
    if (!profile) throw new Error("World profile not found");
    const connection = JSON.parse(profile.connection_json || "{}");
    const address = String(connection.address || connection.internalIp || connection.externalIp || "").trim();
    const worldId = String(connection.worldId || profile.server_world_id || "").trim();
    const port = Number(connection.syncPort || 4318);
    const service = ["steam", "epic", "gamepass"].includes(connection.service) ? connection.service : (connection.platform === "gamepass" ? "gamepass" : "steam");
    const platform = service === "gamepass" ? "gamepass" : "steam";
    const install = steamlib.normalizeGameInstall(profile.client_install || dbm.getSetting(`clientInstall:${service}`, null));
    if (!address || !worldId || !install || !Number.isInteger(port) || port < 1 || port > 65535) throw new Error("This World profile is missing its Sync endpoint or game installation");
    const base = `http://${address}:${port}/api/sync/public/${encodeURIComponent(worldId)}`;
    const manifestController = new AbortController();
    const manifestTimeout = setTimeout(() => manifestController.abort(), 10000);
    let manifestResponse;
    try { manifestResponse = await fetch(base, { cache: "no-store", signal: manifestController.signal, headers: { "X-RSDW-World-Password": String(connection.password || ""), "X-RSDW-Client-Platform": platform } }); }
    finally { clearTimeout(manifestTimeout); }
    const manifestPayload = await manifestResponse.json().catch(() => ({}));
    if (!manifestResponse.ok || !manifestPayload.manifest) throw new Error(manifestPayload.error || "The World did not return its admission manifest");
    const manifest = manifestPayload.manifest;
    const attestation = syncManifest.createClientAttestation(manifest, install);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    let response;
    try { response = await fetch(`${base}/admission`, { method: "POST", cache: "no-store", signal: controller.signal, headers: { "Content-Type": "application/json", "X-RSDW-World-Password": String(connection.password || ""), "X-RSDW-Client-Platform": platform }, body: JSON.stringify(attestation) }); }
    finally { clearTimeout(timeout); }
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.admission?.approved) throw new Error(payload.error || "The World did not approve this client manifest");
    const { token: _token, ...savedAdmission } = payload.admission;
    dbm.upsertProfile({ profile_id: profile.profile_id, connection: { ...connection, admission: savedAdmission } });
    return NextResponse.json({ ok: true, admission: payload.admission });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.name === "AbortError" ? "The World did not answer the admission request in time" : error.message }, { status: 409 });
  }
}
