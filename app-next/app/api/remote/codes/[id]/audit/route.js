import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Admin-only: the per-code action log. Rows survive the code's deletion (they carry a
// denormalized snapshot), so this reads by code id whether or not the code still exists.
export async function GET(req, { params }) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  const limit = Number(new URL(req.url).searchParams.get("limit")) || 200;
  const rows = dbm.listRemoteAudit(params.id, limit).map((r) => ({
    id: r.id, ts: r.ts, action: r.action, worldId: r.world_id || null,
    detail: r.detail || null, ip: r.ip || null,
  }));
  return NextResponse.json({ ok: true, audit: rows });
}
