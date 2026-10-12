import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const ra = require("@/lib/remoteauth");
const syncManifest = require("@/lib/sync/manifest");
const cloudStorage = require("@/lib/sync/cloud-storage");
const cloudExport = require("@/lib/sync/cloud-export");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods" });
  if (denied) return denied;
  if (!dbm.getWorld(params.id)) return NextResponse.json({ ok: false, error: "World not found" }, { status: 404 });
  if (new URL(req.url).searchParams.get("export") === "status") {
    return NextResponse.json({ ok: true, export: cloudExport.status(params.id) });
  }
  if (new URL(req.url).searchParams.get("template") === "1") {
    const manifest = syncManifest.buildWorldManifest(params.id);
    return NextResponse.json({ ok: true, template: { schema: cloudStorage.SCHEMA, revision: manifest.revision, files: manifest.units.flatMap((unit) => unit.files || []).map((file) => ({ target: file.target, size: file.size, sha256: file.sha256, url: "PASTE_PUBLIC_FILE_LINK" })) } });
  }
  return NextResponse.json({ ok: true, storage: cloudStorage.publicStatus(params.id), providers: Object.values(cloudStorage.PROVIDERS), hostTypes: Object.values(cloudStorage.HOST_TYPES) });
}

export async function POST(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods", action: "mods.sync", mutating: true });
  if (denied) return denied;
  try {
    if (!dbm.getWorld(params.id)) throw new Error("World not found");
    const body = await req.json();
    if (body.prepareExport) return NextResponse.json({ ok: true, export: cloudExport.start(params.id, { platform: body.platform || "steam" }) });
    let storage = cloudStorage.save(params.id, body);
    if (body.refresh && storage.mode !== "local") storage = await cloudStorage.refresh(params.id, syncManifest.buildWorldManifest(params.id));
    return NextResponse.json({ ok: true, storage, providers: Object.values(cloudStorage.PROVIDERS), hostTypes: Object.values(cloudStorage.HOST_TYPES) });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 400 });
  }
}
