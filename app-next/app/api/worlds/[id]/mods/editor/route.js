import { NextResponse } from "next/server";
const lanes = require("@/lib/mod-lanes");
const sup = require("@/lib/supervisor");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods" });
  if (denied) return denied;
  const url = new URL(req.url);
  try {
    return NextResponse.json({ ok: true, file: lanes.readEditableFile(params.id, url.searchParams.get("lane") || "server", url.searchParams.get("path") || "") });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }
}

export async function PUT(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods", action: "mods.sync", mutating: true });
  if (denied) return denied;
  try {
    const body = await req.json();
    const current = lanes.readEditableFile(params.id, body.lane || "server", body.path || "");
    if (sup.isAlive(params.id) && !current.hotload) {
      return NextResponse.json({ ok: false, error: `${current.modName} is not marked HOTLOAD = YES. Stop the server before saving it.` }, { status: 409 });
    }
    const file = lanes.writeEditableFile(params.id, body.lane || "server", body.path || "", body.content, body.etag);
    return NextResponse.json({ ok: true, file });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }
}
