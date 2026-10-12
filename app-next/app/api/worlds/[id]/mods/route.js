import { NextResponse } from "next/server";
const mods = require("@/lib/mod-lanes");
const sup = require("@/lib/supervisor");
const ra = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods" });
  if (denied) return denied;
  try { return NextResponse.json({ ok: true, ...mods.status(params.id) }); }
  catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}

export async function PATCH(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods", action: "mods.sync", mutating: true });
  if (denied) return denied;
  if (sup.isAlive(params.id)) return NextResponse.json({ ok: false, error: "Stop the server before changing its PAK destination." }, { status: 409 });
  try {
    const body = await req.json();
    return NextResponse.json({ ok: true, ...mods.setPakInstallMode(params.id, body.pakInstallMode) });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}
