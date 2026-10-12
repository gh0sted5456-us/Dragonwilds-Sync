import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const active = require("@/lib/active-server-profile");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  const activeId = active.readActiveId();
  const world = activeId ? dbm.getWorld(activeId) : null;
  return NextResponse.json({ ok: true, activeId, world, settings: world ? active.settingsFor(world) : null });
}

export async function POST(req) {
  try {
    const { worldId } = await req.json();
    const result = active.activate(String(worldId || ""));
    return NextResponse.json({ ok: true, activeId: result.world.world_id, ...result });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}
