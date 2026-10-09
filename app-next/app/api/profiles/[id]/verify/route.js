import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const syncManifest = require("@/lib/sync/manifest");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(_req, { params }) {
  try {
    const profile = dbm.getProfile(params.id);
    if (!profile) throw new Error("Profile not found");
    const connection = JSON.parse(profile.connection_json || "{}");
    const address = String(connection.address || connection.internalIp || connection.externalIp || "").trim();
    const worldId = String(connection.worldId || profile.server_world_id || "").trim();
    const port = Number(connection.syncPort || 4318);
    if (!address || !worldId || !Number.isInteger(port) || port < 1 || port > 65535) throw new Error("This profile does not have a complete Sync endpoint.");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    let response;
    try { response = await fetch(`http://${address}:${port}/api/sync/public/${encodeURIComponent(worldId)}`, { cache: "no-store", signal: controller.signal, headers: { "X-RSDW-World-Password": String(connection.password || "") } }); }
    finally { clearTimeout(timeout); }
    const payload = await response.json();
    if (!response.ok || !payload.manifest) throw new Error(payload.error || "The World did not return a Sync manifest.");
    const platform = connection.platform === "gamepass" ? "gamepass" : "steam";
    const install = dbm.getSetting(`clientInstall:${platform}`, null);
    if (!install) throw new Error(`Application Setup -> Play -> ${platform === "gamepass" ? "PC Game Pass" : "Steam"} is not configured.`);
    const comparison = syncManifest.compareManifest(payload.manifest, install);
    const identity = payload.manifest.world?.identity || {};
    const nextConnection = {
      ...connection,
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
  } catch (e) { return NextResponse.json({ ok: false, error: e.name === "AbortError" ? "The World did not respond in time." : e.message }, { status: 400 }); }
}
