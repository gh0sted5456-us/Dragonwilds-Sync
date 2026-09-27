import { NextResponse } from "next/server";
const syncManifest = require("@/lib/sync/manifest");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(_req, { params }) {
  try {
    const manifest = syncManifest.buildWorldManifest(params.id);
    return NextResponse.json({ ok: true, manifest });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 404 }); }
}
