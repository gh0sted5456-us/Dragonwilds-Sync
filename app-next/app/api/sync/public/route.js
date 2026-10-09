import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const syncManifest = require("@/lib/sync/manifest");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function preview(world, manifest) {
  return {
    worldId: world.world_id,
    name: manifest.world.name,
    gamePort: manifest.world.gamePort,
    syncPort: Number(process.env.APP_MANAGER_SHARE_PORT || process.env.APP_MANAGER_PORT || 4318),
    revision: manifest.revision,
    modCount: manifest.units.length,
    modBadges: [...new Set(manifest.units.map((unit) => String(unit.type || "mod").toUpperCase()))],
    identity: manifest.world.identity,
    rules: manifest.world.rules,
    units: manifest.units.map((unit) => ({ key: unit.key, name: unit.name, type: unit.type, fileCount: unit.fileCount, bytes: unit.bytes, clientRequired: unit.clientRequired !== false })),
  };
}

export async function GET(req) {
  const platform = req.headers.get("x-rsdw-client-platform") === "gamepass" ? "gamepass" : "steam";
  const worlds = [];
  for (const world of dbm.listWorlds()) {
    try { worlds.push(preview(world, syncManifest.buildWorldManifest(world.world_id, { platform }))); }
    catch { /* an incomplete local profile should not hide healthy Worlds */ }
  }
  return NextResponse.json({ ok: true, protocol: syncManifest.PROTOCOL, protocolVersion: syncManifest.PROTOCOL_VERSION, worlds });
}
