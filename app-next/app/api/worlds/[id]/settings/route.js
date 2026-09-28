import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const ini = require("@/lib/ini");
const active = require("@/lib/active-server-profile");
const { GROUPS } = require("@/lib/palfields");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Keys the app manages itself — never surfaced to the editor, always re-applied
// from the world record so the editor can't break the world's identity.
// PublicIP and PublicPort are intentionally NOT managed here — they're the address
// advertised to the community browser and are user-editable in Server Identity (so
// a tunnel like playit.gg can be pointed to). Everything else stays app-controlled.
const MANAGED = new Set([
  "RESTAPIPort", "RESTAPIEnabled",
  "AdminPassword", "WorldPassword", "OwnerId", "ServerName", "DefaultWorldName",
]);

export async function GET(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "settings" });
  if (denied) return denied;
  const s = active.settingsFor(w);
  // Report which keys are actually present in the ini so the editor can show
  // "set" vs "default (not written)" and only save real changes.
  const presentKeys = Object.keys(s.values).filter((k) => !MANAGED.has(k));
  return NextResponse.json({
    ok: true, path: s.path, exists: s.exists,
    options: s.values, presentKeys, groups: GROUPS,
    active: active.readActiveId() === w.world_id,
  });
}

export async function POST(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "settings", action: "settings.save", mutating: true });
  if (denied) return denied;

  // The editor sends ONLY the keys the user actually changed (`changed`), plus
  // the full set it's aware of is irrelevant — we merge changes onto the CURRENT
  // ini so untouched settings (and any keys the editor doesn't know about) are
  // preserved exactly as Palworld wrote them.
  const body = await req.json();
  const changed = body.changed || body.options || {};

  const unquote = (value) => {
    const text = value == null ? "" : String(value);
    if ((text.startsWith('"') && text.endsWith('"')) || (text.startsWith("'") && text.endsWith("'"))) {
      return text.slice(1, -1);
    }
    return text;
  };

  // Persist password changes to the world record first, so managed re-apply
  // below uses the latest saved values instead of stale DB values.
  const worldUpdates = {};
  if (Object.prototype.hasOwnProperty.call(changed, "AdminPassword")) {
    worldUpdates.admin_password = unquote(changed.AdminPassword);
  }
  if (Object.prototype.hasOwnProperty.call(changed, "WorldPassword")) {
    worldUpdates.server_password = unquote(changed.WorldPassword);
  }
  if (Object.keys(worldUpdates).length) {
    dbm.updateWorld(params.id, worldUpdates);
    if ("admin_password" in worldUpdates) w.admin_password = worldUpdates.admin_password;
    if ("server_password" in worldUpdates) w.server_password = worldUpdates.server_password;
  }

  const freshWorld = dbm.getWorld(params.id);
  const profile = active.settingsFor(freshWorld);
  const merged = { ...profile.values };

  for (const [k, v] of Object.entries(changed)) {
    if (MANAGED.has(k) || v === undefined || v === null) continue;
    merged[k] = v;
  }

  const normalized = ini.withWorldNetworkSettings(merged, freshWorld);
  const saved = active.saveSettings(freshWorld.world_id, normalized, { baseRaw: profile.content });
  const isActive = active.readActiveId() === freshWorld.world_id;
  if (isActive) active.materialize(freshWorld);

  const running = require("@/lib/supervisor").isAlive(freshWorld.world_id);
  dbm.logEvent(
    freshWorld.world_id,
    "settings",
    `Saved ${Object.keys(changed).length} change(s) to Server profile${running ? " (restart to apply)" : ""}`
  );
  return NextResponse.json({
    ok: true,
    path: saved.path,
    written: Object.keys(normalized).length,
    running,
    active: isActive,
  });
}
