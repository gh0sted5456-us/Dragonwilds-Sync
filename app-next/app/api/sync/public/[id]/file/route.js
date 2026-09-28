import { NextResponse } from "next/server";
const fs = require("fs");
const syncManifest = require("@/lib/sync/manifest");
const { authorizeWorldRequest } = require("@/lib/sync/auth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  try {
    const auth = authorizeWorldRequest(params.id, req);
    if (!auth.ok) return NextResponse.json({ ok: false, error: auth.error }, { status: auth.status });
    const target = new URL(req.url).searchParams.get("target");
    const platform = req.headers.get("x-rsdw-client-platform") === "gamepass" ? "gamepass" : "steam";
    const file = syncManifest.resolveWorldFile(params.id, target, { platform });
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
