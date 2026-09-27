import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const { createBackup } = require("@/lib/backups");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "backups" });
  if (denied) return denied;
  return NextResponse.json({ ok: true, backups: dbm.listBackups(params.id) });
}

export async function POST(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "backups", action: "backup.create", mutating: true });
  if (denied) return denied;
  try {
    const r = await createBackup(params.id, "manual");
    return NextResponse.json({ ok: true, backup: r });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 500 });
  }
}
