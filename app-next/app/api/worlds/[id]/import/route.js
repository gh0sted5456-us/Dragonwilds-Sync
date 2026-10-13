import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const ra = require("@/lib/remoteauth");
const repository = require("@/lib/world-repository");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  const world = dbm.getWorld(params.id);
  if (!world) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "backups", action: "world.import-save", mutating: true });
  if (denied) return denied;
  try {
    const { savePath, repositoryId, worldType } = await req.json();
    if (repositoryId && worldType) {
      const item = repository.setWorldType(repositoryId, worldType);
      return NextResponse.json({ ok: true, item, repository: repository.listWorlds() });
    }
    if (!savePath) return NextResponse.json({ ok: false, error: "No save file selected" }, { status: 400 });
    const item = repository.importWorld(savePath);
    return NextResponse.json({ ok: true, item, repository: repository.listWorlds() });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }
}
