import { NextResponse } from "next/server";
const mods = require("@/lib/mod-lanes");
const ra = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods", action: "mods.source", mutating: true });
  if (denied) return denied;
  try {
    const body = await req.json();
    return NextResponse.json({ ok: true, ...mods.setRequiredSource(params.id, body.path) });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}
