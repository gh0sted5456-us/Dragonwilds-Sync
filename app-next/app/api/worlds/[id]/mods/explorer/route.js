import { NextResponse } from "next/server";
const lanes = require("@/lib/mod-lanes");
const ra = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export async function GET(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods" });
  if (denied) return denied;
  const url = new URL(req.url);
  try { return NextResponse.json({ ok: true, ...lanes.browse(params.id, url.searchParams.get("lane") || "server", url.searchParams.get("path") || "") }); }
  catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}
