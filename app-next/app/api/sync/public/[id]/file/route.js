import { NextResponse } from "next/server";
const fs = require("fs");
const { Readable } = require("stream");
const syncManifest = require("@/lib/sync/manifest");
const { authorizeWorldDownload } = require("@/lib/sync/auth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  try {
    const url = new URL(req.url);
    const target = url.searchParams.get("target");
    const platform = req.headers.get("x-rsdw-client-platform") === "gamepass" || url.searchParams.get("platform") === "gamepass" ? "gamepass" : "steam";
    const file = syncManifest.resolveWorldFile(params.id, target, { platform });
    const auth = authorizeWorldDownload(params.id, file, req);
    if (!auth.ok) return NextResponse.json({ ok: false, error: auth.error }, { status: auth.status });
    return new NextResponse(Readable.toWeb(fs.createReadStream(file.source)), {
      headers: {
        "Content-Type": "application/octet-stream",
        "Content-Length": String(file.size),
        "X-RSDW-SHA256": file.sha256,
        "Cache-Control": "no-store",
      },
    });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 404 }); }
}
