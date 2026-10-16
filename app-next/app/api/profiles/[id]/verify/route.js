import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const syncManifest = require("@/lib/sync/manifest");
const steamlib = require("@/lib/steamlibrary");
const remoteauth = require("@/lib/remoteauth");
const { safeSyncText } = require("@/lib/sync-progress");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  if (!remoteauth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  try {
    const profile = dbm.getProfile(params.id);
    if (!profile) throw new Error("Profile not found");
    const connection = JSON.parse(profile.connection_json || "{}");
    const address = String(connection.address || connection.internalIp || connection.externalIp || "").trim();
    const worldId = String(connection.worldId || profile.server_world_id || "").trim();
    const port = Number(connection.syncPort || 4318);
    const service = ["steam", "epic", "gamepass"].includes(connection.service) ? connection.service : (connection.platform === "gamepass" ? "gamepass" : "steam");
    const platform = service === "gamepass" ? "gamepass" : "steam";
    if (!address || !worldId || !Number.isInteger(port) || port < 1 || port > 65535) throw new Error("This profile does not have a complete Sync endpoint.");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    let response, payload;
    try {
      response = await fetch(`http://${address}:${port}/api/sync/public/${encodeURIComponent(worldId)}`, { cache: "no-store", signal: controller.signal, redirect: "error", headers: { "X-RSDW-World-Password": String(connection.password || ""), "X-RSDW-Client-Platform": platform } });
      payload = await response.json();
    }
    finally { clearTimeout(timeout); }
    if (!response.ok || !payload.manifest) throw new Error(payload.error || "The World did not return a Sync manifest.");
    const install = profile.client_install || dbm.getSetting(`clientInstall:${service}`, null);
    if (!install) throw new Error(`This World needs a ${steamlib.serviceLabel(service)} game installation.`);
    const comparison = syncManifest.compareManifest(payload.manifest, install);
    const identity = payload.manifest.world?.identity || {};
    const nextConnection = {
      ...connection,
      deliveryMode: payload.manifest.transport?.storageMode || "local",
      deliveryProvider: payload.manifest.transport?.storageProvider || "local",
      admission: null,
      worldIdentity: {
        iconData: identity.iconData || null,
        bannerData: identity.bannerData || null,
        accentColor: identity.accentColor || null,
      },
      worldType: payload.manifest.world?.type || connection.worldType || "Private",
      rules: payload.manifest.world?.rules || connection.rules || {},
      modBadges: [...new Set((payload.manifest.units || []).map((unit) => String(unit.type || "mod").toUpperCase()))],
      modCount: (payload.manifest.units || []).length,
    };
    dbm.upsertProfile({
      profile_id: profile.profile_id,
      display_name: payload.manifest.world?.name || profile.display_name,
      connection: nextConnection,
      last_manifest_revision: payload.manifest.revision,
    });
    return NextResponse.json({ ok: true, manifest: payload.manifest, comparison });
  } catch (e) { return NextResponse.json({ ok: false, error: e.name === "AbortError" ? "The World did not respond in time." : safeSyncText(e.message) }, { status: 400 }); }
}
