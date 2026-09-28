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
  if (!Object.keys(ini.parseOptionSettings(content)).length) {
    return NextResponse.json({ ok: false, error: "DedicatedServer.ini contains no settings" }, { status: 400 });
  }

  const current = active.settingsFor(w);
  if (current.content) dbm.insertIniVersion(w.world_id, current.content, "before edit");

  const saved = active.saveRawSettings(w.world_id, content);
  const isActive = active.readActiveId() === w.world_id;
  if (isActive) active.materialize(w);

  dbm.insertIniVersion(w.world_id, saved.content, "saved");
  const running = sup.isAlive(w.world_id);
  dbm.logEvent(w.world_id, "settings", `Edited Server profile DedicatedServer.ini${running ? " (restart to apply)" : ""}`);
  return NextResponse.json({
    ok: true,
    path: saved.path,
    content: saved.content,
    running,
    active: isActive,
  });
}
