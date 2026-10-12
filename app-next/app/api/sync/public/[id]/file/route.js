import { NextResponse } from "next/server";
const fs = require("fs");
const { Readable } = require("stream");
const syncManifest = require("@/lib/sync/manifest");
const cloudStorage = require("@/lib/sync/cloud-storage");
const { authorizeWorldDownload, authorizeProfileDownload } = require("@/lib/sync/auth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  try {
    const url = new URL(req.url);
    const target = url.searchParams.get("target");
    const platform = req.headers.get("x-rsdw-client-platform") === "gamepass" || url.searchParams.get("platform") === "gamepass" ? "gamepass" : "steam";
    const playerShare = String(params.id).startsWith("profile-");
    const profileId = playerShare ? String(params.id).slice("profile-".length) : null;
    const file = playerShare ? syncManifest.resolveProfileFile(profileId, target) : syncManifest.resolveWorldFile(params.id, target, { platform });
    const auth = playerShare ? authorizeProfileDownload(profileId, file, req) : authorizeWorldDownload(params.id, file, req);
    if (!auth.ok) return NextResponse.json({ ok: false, error: auth.error }, { status: auth.status });
    if (!playerShare && url.searchParams.get("source") !== "local") {
      const remote = cloudStorage.resolveRemoteFile(params.id, file);
      if (remote.url) return NextResponse.redirect(remote.url, { status: 307, headers: { "Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer", "X-RSDW-Storage-Provider": remote.provider } });
    }
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
