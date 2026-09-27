import { NextResponse } from "next/server";
const syncManifest = require("@/lib/sync/manifest");
const ra = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods", action: "sync.manifest", mutating: false });
  if (denied) return denied;
  try { return NextResponse.json({ ok: true, manifest: syncManifest.buildWorldManifest(params.id) }); }
  catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}
