import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const ini = require("@/lib/ini");
const active = require("@/lib/active-server-profile");
const sup = require("@/lib/supervisor");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "settings" });
  if (denied) return denied;

  const profile = active.settingsFor(w);
  return NextResponse.json({
    ok: true,
    path: profile.path,
    exists: profile.exists,
    content: profile.content,
    running: sup.isAlive(w.world_id),
    active: active.readActiveId() === w.world_id,
  });
}

export async function POST(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "settings", action: "ini.save", mutating: true });
  if (denied) return denied;

  const { content } = await req.json();
  if (typeof content !== "string") {
    return NextResponse.json({ ok: false, error: "content required" }, { status: 400 });
  }
  const parsed = ini.parseOptionSettings(content);
  if (!Object.keys(parsed).length) {
    return NextResponse.json({ ok: false, error: "DedicatedServer.ini contains no settings" }, { status: 400 });
  }

  const current = active.settingsFor(w);
  if (current.content) dbm.insertIniVersion(w.world_id, current.content, "before edit");

  let freshWorld;
  try {
    freshWorld = active.updateWorldFromSettings(w, parsed);
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: error.statusCode || 400 });
  }

  const saved = active.saveRawSettings(freshWorld.world_id, content);
  const materialized = active.materializeActiveBestEffort(freshWorld);
  if (materialized.warning) dbm.logEvent(freshWorld.world_id, "settings", materialized.warning);

  dbm.insertIniVersion(w.world_id, saved.content, "saved");
  const running = sup.isAlive(w.world_id);
  dbm.logEvent(w.world_id, "settings", `Edited Server profile DedicatedServer.ini${running ? " (restart to apply)" : ""}`);
  return NextResponse.json({
    ok: true,
    path: saved.path,
    content: saved.content,
    running,
    active: materialized.active,
    materializeWarning: materialized.warning,
  });
}
