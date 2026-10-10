import { NextResponse } from "next/server";
const provision = require("@/lib/provision");
const dbm = require("@/lib/db");
const sup = require("@/lib/supervisor");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  if (!dbm.getWorld(params.id)) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "backups" });
  if (denied) return denied;
  try {
    return NextResponse.json({ ok: true, slots: provision.listSaveSlots(params.id), running: sup.isAlive(params.id) });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }
}

export async function POST(req, { params }) {
  if (!dbm.getWorld(params.id)) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "backups", action: "world.activate-save", mutating: true });
  if (denied) return denied;
  try {
    const body = await req.json();
    const result = await provision.activateSaveSlot(params.id, body.name, { backupFirst: true });
    return NextResponse.json({ ok: true, result });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }
}
