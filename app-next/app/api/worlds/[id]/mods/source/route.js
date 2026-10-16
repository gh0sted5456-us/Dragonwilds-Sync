import { NextResponse } from "next/server";
const mods = require("@/lib/mod-lanes");
const sup = require("@/lib/supervisor");
const ra = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods", action: "mods.source", mutating: true });
  if (denied) return denied;
  try {
    const body = await req.json();
    const result = await sup.runMaintenance(params.id, () => mods.setRequiredSource(params.id, body.path));
    return NextResponse.json({ ok: true, ...result });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}
