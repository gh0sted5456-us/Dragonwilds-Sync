import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const sup = require("@/lib/supervisor");
const runtimes = require("@/lib/runtime-packages");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods" });
  if (denied) return denied;
  return NextResponse.json({ ok: true, packages: runtimes.status(params.id) });
}

export async function POST(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods", action: "runtime.install", mutating: true });
  if (denied) return denied;
  if (sup.isRunning(w.world_id) || sup.pidAlive(w.process_id)) {
    return NextResponse.json({ ok: false, error: "Stop the world before replacing its UE4SS or RuneSchema runtime." }, { status: 409 });
  }
  const body = await req.json().catch(() => ({}));
  try {
    const packages = runtimes.install(params.id, body.component, body.zipPath);
    const kind = String(body.component || "").toLowerCase();
    const label = kind === "ue4ss-gamepass" ? "UE4SS · PC Game Pass" : kind === "ue4ss-steam" ? "UE4SS · Steam/server" : "RuneSchema";
    dbm.logEvent(params.id, "mods", `Installed managed ${label} runtime package for host + client Sync`);
    return NextResponse.json({ ok: true, packages });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}
