import { NextResponse } from "next/server";
const sup = require("@/lib/supervisor");
const ra = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export async function GET(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "console" });
  if (denied) return denied;
  return NextResponse.json({ ok: true, lines: sup.getLogs(params.id) });
}
