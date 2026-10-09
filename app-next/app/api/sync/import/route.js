import { NextResponse } from "next/server";
import crypto from "crypto";
const dbm = require("@/lib/db");
const syncManifest = require("@/lib/sync/manifest");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const publicProfile = (row) => ({ ...row, connection: JSON.parse(row.connection_json || "{}"), connection_json: undefined });

export async function POST(req) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const body = await req.json();
    const address = String(body.address || "").trim();
    const worldId = String(body.worldId || "").trim();
    const syncPort = Number(body.syncPort || 4318);
    const platform = body.platform === "gamepass" ? "gamepass" : "steam";
    if (!/^[a-zA-Z0-9._:-]+$/.test(address) || !worldId || !Number.isInteger(syncPort) || syncPort < 1 || syncPort > 65535) throw new Error("Enter a valid server address and Sync port.");
    const response = await fetch(`http://${address}:${syncPort}/api/sync/public/${encodeURIComponent(worldId)}`, {
      cache: "no-store", signal: controller.signal,
      headers: { "X-RSDW-World-Password": String(body.password || ""), "X-RSDW-Client-Platform": platform },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.manifest) throw new Error(payload.error || "The server did not return its manifest.");
    const manifest = payload.manifest;
    if (manifest.protocol !== syncManifest.PROTOCOL || manifest.protocolVersion !== syncManifest.PROTOCOL_VERSION) throw new Error("The server uses an incompatible Sync manifest.");
    const identity = manifest.world?.identity || {};
    const rules = manifest.world?.rules || {};
    const modBadges = [...new Set((manifest.units || []).map((unit) => String(unit.type || "mod").toUpperCase()))];
    const existing = dbm.listProfiles().find((profile) => profile.server_world_id === worldId && JSON.parse(profile.connection_json || "{}").address === address);
    const row = dbm.upsertProfile({
      profile_id: existing?.profile_id || crypto.randomUUID(),
      display_name: manifest.world?.name || "Dragonwilds World",
      server_world_id: worldId,
      client_install: null,
      last_manifest_revision: manifest.revision,
      connection: { address, syncPort, worldId, password: String(body.password || ""), platform, worldIdentity: identity, worldType: manifest.world?.type || "Private", rules, modBadges, modCount: (manifest.units || []).length, manifestDownloadedAt: Date.now() },
    });
    return NextResponse.json({ ok: true, profile: publicProfile(row), manifest });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.name === "AbortError" ? "The server did not respond in time." : e.message }, { status: 400 });
  } finally { clearTimeout(timeout); }
}
