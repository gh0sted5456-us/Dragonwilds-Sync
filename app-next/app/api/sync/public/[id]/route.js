import { NextResponse } from "next/server";
const syncManifest = require("@/lib/sync/manifest");
const { authorizeWorldRequest } = require("@/lib/sync/auth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  try {
    const auth = authorizeWorldRequest(params.id, req);
    if (!auth.ok) return NextResponse.json({ ok: false, error: auth.error }, { status: auth.status });
    const platform = req.headers.get("x-rsdw-client-platform") === "gamepass" ? "gamepass" : "steam";
    const host = req.headers.get("x-forwarded-host") || req.headers.get("host");
    const protocol = req.headers.get("x-forwarded-proto") || new URL(req.url).protocol.replace(":", "");
    const baseUrl = `${protocol}://${host}/api/sync/public/${encodeURIComponent(params.id)}`;
    const manifest = syncManifest.withDownloadUrls(params.id, syncManifest.buildWorldManifest(params.id, { platform }), baseUrl);
    return NextResponse.json({ ok: true, manifest });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 404 }); }
}
