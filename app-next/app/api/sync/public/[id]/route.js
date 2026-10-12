import { NextResponse } from "next/server";
const syncManifest = require("@/lib/sync/manifest");
const { authorizeWorldRequest, authorizeProfileRequest } = require("@/lib/sync/auth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  try {
    const playerShare = String(params.id).startsWith("profile-");
    const profileId = playerShare ? String(params.id).slice("profile-".length) : null;
    const auth = playerShare ? authorizeProfileRequest(profileId, req) : authorizeWorldRequest(params.id, req);
    if (!auth.ok) return NextResponse.json({ ok: false, error: auth.error }, { status: auth.status });
    const platform = req.headers.get("x-rsdw-client-platform") === "gamepass" ? "gamepass" : "steam";
    const host = req.headers.get("x-forwarded-host") || req.headers.get("host");
    const protocol = req.headers.get("x-forwarded-proto") || new URL(req.url).protocol.replace(":", "");
    const baseUrl = `${protocol}://${host}/api/sync/public/${encodeURIComponent(params.id)}`;
    const source = playerShare ? syncManifest.buildProfileManifest(profileId) : syncManifest.buildWorldManifest(params.id, { platform });
    const manifest = syncManifest.withDownloadUrls(params.id, source, baseUrl);
    return NextResponse.json({ ok: true, manifest });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 404 }); }
}
