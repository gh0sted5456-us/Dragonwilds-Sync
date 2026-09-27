import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const sup = require("@/lib/supervisor");
const ue4ss = require("@/lib/ue4ss");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// GET: UE4SS install status + Lua mod list for this world.
export async function GET(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods" });
  if (denied) return denied;
  return NextResponse.json({ ok: true, ...ue4ss.status(w.install_dir) });
}

// PATCH: force GuiConsoleVisible=0 (a manually-installed UE4SS with the console on
// crashes a dedicated server). Idempotent.
export async function PATCH(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods", action: "ue4ss.fixConsole", mutating: true });
  if (denied) return denied;
  const fixed = ue4ss.ensureGuiConsoleDisabled(w.install_dir);
  if (fixed) dbm.logEvent(params.id, "mods", "Disabled UE4SS GUI console (dedicated-server safety)");
  return NextResponse.json({ ok: true, fixed, ...ue4ss.status(w.install_dir) });
}

// POST: install UE4SS from a user-provided zip path. Refused while running.
export async function POST(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods", action: "ue4ss.install", mutating: true });
  if (denied) return denied;
  if (sup.isRunning(w.world_id) || sup.pidAlive(w.process_id)) {
    return NextResponse.json({ ok: false, error: "Stop the world before installing UE4SS." }, { status: 409 });
  }
  const { zipPath } = await req.json().catch(() => ({}));
  if (!zipPath) return NextResponse.json({ ok: false, error: "Provide the UE4SS zip path." }, { status: 400 });
  try {
    const res = ue4ss.install(w.install_dir, zipPath);
    dbm.logEvent(params.id, "mods", "Installed UE4SS");
    return NextResponse.json({ ok: true, ...res });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}
