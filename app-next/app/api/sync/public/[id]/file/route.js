import { NextResponse } from "next/server";
const fs = require("fs");
const syncManifest = require("@/lib/sync/manifest");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  try {
    const target = new URL(req.url).searchParams.get("target");
    const file = syncManifest.resolveWorldFile(params.id, target);
    return new NextResponse(fs.readFileSync(file.source), {
      headers: {
        "Content-Type": "application/octet-stream",
        "Content-Length": String(file.size),
        "X-RSDW-SHA256": file.sha256,
        "Cache-Control": "no-store",
      },
    });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 404 }); }
}
