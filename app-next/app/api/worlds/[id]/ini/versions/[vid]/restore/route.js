import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const ini = require("@/lib/ini");
const active = require("@/lib/active-server-profile");
const sup = require("@/lib/supervisor");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "settings", action: "ini.restore", mutating: true });
  if (denied) return denied;

  const v = dbm.getIniVersion(w.world_id, Number(params.vid));
  if (!v) return NextResponse.json({ ok: false, error: "version not found" }, { status: 404 });

  const current = active.settingsFor(w);
  if (current.content) dbm.insertIniVersion(w.world_id, current.content, "before restore");

  let freshWorld;
  try {
    freshWorld = active.updateWorldFromSettings(w, ini.parseOptionSettings(v.content));
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: error.statusCode || 400 });
  }

  const saved = active.saveRawSettings(freshWorld.world_id, v.content);
  const materialized = active.materializeActiveBestEffort(freshWorld);
  if (materialized.warning) dbm.logEvent(freshWorld.world_id, "settings", materialized.warning);

  dbm.insertIniVersion(w.world_id, saved.content, `restored from #${v.id}`);
  const running = sup.isAlive(w.world_id);
  dbm.logEvent(w.world_id, "settings", `Restored Server profile settings from history #${v.id}${running ? " (restart to apply)" : ""}`);
  return NextResponse.json({
    ok: true,
    path: saved.path,
    content: saved.content,
    running,
    active: materialized.active,
    materializeWarning: materialized.warning,
  });
}
