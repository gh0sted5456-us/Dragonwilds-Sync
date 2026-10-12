import { NextResponse } from "next/server";
const syncManifest = require("@/lib/sync/manifest");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req) {
  try {
    const { manifest, gameInstall } = await req.json();
    return NextResponse.json({ ok: true, ...syncManifest.compareManifest(manifest, gameInstall) });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}
