import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const caps = require("@/lib/player-cap");
const ra = require("@/lib/remoteauth");
const sup = require("@/lib/supervisor");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "settings" });
  if (denied) return denied;
  const world = dbm.getWorld(params.id);
  if (!world) return NextResponse.json({ ok: false, error: "World not found" }, { status: 404 });
  try {
    return NextResponse.json({ ok: true, ...caps.settingsFor(world), running: sup.isAlive(params.id), active: dbm.getSetting("activeServerWorldId", "") === params.id });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }
}

export async function POST(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "settings", action: "settings.save", mutating: true });
  if (denied) return denied;
  const world = dbm.getWorld(params.id);
  if (!world) return NextResponse.json({ ok: false, error: "World not found" }, { status: 404 });
  try {
    const { maxPlayers } = await req.json();
    const saved = caps.save(params.id, maxPlayers);
    const running = sup.isAlive(params.id);
    const active = dbm.getSetting("activeServerWorldId", "") === params.id;
    let warning = null;
    let applied = false;
    if (active && !running) {
      try { caps.materialize(world); applied = true; }
      catch (error) { warning = `Player cap saved; Game.ini will be retried at launch: ${error.message}`; }
    }
    dbm.logEvent(params.id, "settings", `Player cap set to ${saved.maxPlayers}${running ? " (restart to apply)" : ""}`);
    return NextResponse.json({ ok: true, ...saved, running, active, applied, warning });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }
}
