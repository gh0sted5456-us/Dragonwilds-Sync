import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const ue4ss = require("@/lib/ue4ss");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// POST: manage UE4SS Lua mods for this world.
//   { action: "toggle", name, enabled }
//   { action: "import", zipPath }
//   { action: "remove", name }
export async function POST(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods", action: "ue4ss.mods", mutating: true });
  if (denied) return denied;
  const body = await req.json().catch(() => ({}));
  try {
    if (body.action === "toggle") {
      const mods = ue4ss.setModEnabled(w.install_dir, body.name, !!body.enabled);
      dbm.logEvent(params.id, "mods", `${body.enabled ? "Enabled" : "Disabled"} UE4SS mod ${body.name} (restart to apply)`);
      return NextResponse.json({ ok: true, mods });
    }
    if (body.action === "import") {
      if (!body.zipPath) return NextResponse.json({ ok: false, error: "Provide the mod zip path." }, { status: 400 });
      const result = ue4ss.importModZip(w.install_dir, body.zipPath);
      dbm.logEvent(params.id, "mods", `Imported UE4SS mod ${result.name}`);
      return NextResponse.json({ ok: true, result, mods: ue4ss.listMods(w.install_dir) });
    }
    if (body.action === "remove") {
      const mods = ue4ss.removeMod(w.install_dir, body.name);
      dbm.logEvent(params.id, "mods", `Removed UE4SS mod ${body.name}`);
      return NextResponse.json({ ok: true, mods });
    }
    return NextResponse.json({ ok: false, error: "Unknown action." }, { status: 400 });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}
