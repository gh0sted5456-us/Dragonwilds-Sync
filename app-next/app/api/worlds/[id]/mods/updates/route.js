import { NextResponse } from "next/server";
const lanes = require("@/lib/mod-lanes");
const providers = require("@/lib/mod-providers");
const remote = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  const denied = remote.guardResponse(req, { worldId: params.id, tab: "mods" });
  if (denied) return denied;
  try {
    const snapshot = lanes.status(params.id);
    const mods = snapshot.modLanes.flatMap((lane) => lane.mods || []).filter((mod) => mod.identity);
    const entries = [];
    for (const mod of mods) entries.push([mod.selectionKey, await providers.checkMod(mod.identity)]);
    return NextResponse.json({ ok: true, updates: Object.fromEntries(entries), checkedAt: new Date().toISOString() });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }
}
