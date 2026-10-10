import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const ini = require("@/lib/ini");
const active = require("@/lib/active-server-profile");
const { GROUPS } = require("@/lib/palfields");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Identity/auth keys are stored in the World record and mirrored into each
// profile-owned DedicatedServer.ini. They are editable here, but their durable
// source of truth is the World profile rather than whichever INI is live on disk.
// PublicIP/PublicPort remain ordinary INI values so tunnel overrides survive.
const NETWORK_MANAGED = new Set(["RESTAPIPort", "RESTAPIEnabled"]);

export async function GET(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "settings" });
  if (denied) return denied;
  const s = active.settingsFor(w);
  // Report which keys are actually present in the ini so the editor can show
  // "set" vs "default (not written)" and only save real changes.
  const presentKeys = Object.keys(s.values);
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
  // preserved exactly as the dedicated server wrote them.
  const body = await req.json();
  const changed = body.changed || body.options || {};

  // Managed fields live in the World record. The old editor only persisted
  // the two passwords, so OwnerId / ServerName / DefaultWorldName appeared to
  // save and then vanished at launch. Persist every managed field before the
  // profile snapshot is normalized.
  let freshWorld;
  try {
    freshWorld = active.updateWorldFromSettings(w, changed);
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: error.statusCode || 400 });
  }
  const profile = active.settingsFor(freshWorld);
  const merged = { ...profile.values };

  for (const [k, v] of Object.entries(changed)) {
    if (NETWORK_MANAGED.has(k) || active.isWorldManagedSetting(k) || v === undefined || v === null) continue;
    merged[k] = v;
  }

  const normalized = ini.withWorldNetworkSettings(merged, freshWorld);
  const saved = active.saveSettings(freshWorld.world_id, normalized, { baseRaw: profile.content });
  const materialized = active.materializeActiveBestEffort(freshWorld);
  if (materialized.warning) dbm.logEvent(freshWorld.world_id, "settings", materialized.warning);

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
    active: materialized.active,
    materializeWarning: materialized.warning,
  });
}
