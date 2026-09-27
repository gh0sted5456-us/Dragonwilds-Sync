import { NextResponse } from "next/server";
const { restoreBackup } = require("@/lib/backups");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "backups", action: "backup.restore", mutating: true });
  if (denied) return denied;
  const { backupId } = await req.json();
  try {
    const r = await restoreBackup(params.id, backupId);
    return NextResponse.json({ ok: true, result: r });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 500 });
  }
}
