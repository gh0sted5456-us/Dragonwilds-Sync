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
  try {
    const body = await req.json();
    const result = await sup.runMaintenance(params.id, () => mods.setPakInstallMode(params.id, body.pakInstallMode));
    return NextResponse.json({ ok: true, ...result });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}

export async function PUT(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods", action: "mods.sync", mutating: true });
  if (denied) return denied;
  try {
    const body = await req.json();
    const result = await sup.runMaintenance(params.id, () => mods.setLoaderEnabled(params.id, body.lane, body.selectionKey, body.enabled));
    return NextResponse.json({ ok: true, ...result });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}

export async function DELETE(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods", action: "mods.sync", mutating: true });
  if (denied) return denied;
  try {
    const body = await req.json();
    if (typeof body?.selectionKey !== "string") throw new Error("Choose a detected server mod to delete.");
    const result = await sup.runMaintenance(params.id, () => mods.deleteServerMod(params.id, body.selectionKey));
    return NextResponse.json({ ok: true, ...result });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}
