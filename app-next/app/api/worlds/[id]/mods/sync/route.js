import { NextResponse } from "next/server";
const mods = require("@/lib/mods");
const ra = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods", action: "mods.sync", mutating: true });
  if (denied) return denied;
  try {
    const { keys } = await req.json();
    return NextResponse.json({ ok: true, ...mods.syncLaneSelections(params.id, Array.isArray(keys) ? keys : []) });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}
