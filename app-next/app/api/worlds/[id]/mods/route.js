import { NextResponse } from "next/server";
const mods = require("@/lib/mod-lanes");
const ra = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods" });
  if (denied) return denied;
  try { return NextResponse.json({ ok: true, ...mods.status(params.id) }); }
  catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}
