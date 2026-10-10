import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const provision = require("@/lib/provision");
const ra = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  const world = dbm.getWorld(params.id);
  if (!world) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "backups", action: "world.import-save", mutating: true });
  if (denied) return denied;
  const { savePath } = await req.json();
  if (!savePath) return NextResponse.json({ ok: false, error: "No save file selected" }, { status: 400 });
  try {
    const check = await provision.importSave(params.id, savePath, { backupFirst: true });
    return NextResponse.json({ ok: true, check });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }
}
