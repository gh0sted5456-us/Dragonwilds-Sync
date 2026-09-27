import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Edit a pending scheduled broadcast's message and/or time.
export async function PATCH(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "broadcast", action: "broadcast.edit", mutating: true });
  if (denied) return denied;
  const body = await req.json();
  const patch = {};
  if (typeof body.message === "string") {
    const m = body.message.trim();
    if (!m) return NextResponse.json({ ok: false, error: "Message is required" }, { status: 400 });
    patch.message = m;
  }
  if (body.fire_at != null) {
    const fireAt = Number(body.fire_at);
    if (!fireAt || fireAt <= Date.now()) return NextResponse.json({ ok: false, error: "Pick a time in the future." }, { status: 400 });
    patch.fire_at = fireAt;
    // Rescheduling to a future time revives a missed broadcast back to pending.
    patch.status = "pending";
  }
  const updated = dbm.updateBroadcast(params.bid, patch);
  if (!updated) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  return NextResponse.json({ ok: true, broadcast: updated });
}

// Delete (cancel) a pending scheduled broadcast.
export async function DELETE(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "broadcast", action: "broadcast.cancel", mutating: true });
  if (denied) return denied;
  dbm.deleteBroadcast(params.bid);
  return NextResponse.json({ ok: true });
}
