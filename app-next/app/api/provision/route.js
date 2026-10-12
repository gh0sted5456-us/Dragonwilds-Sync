import { NextResponse } from "next/server";
const prov = require("@/lib/provision");
const { conflictsInRegistry } = require("@/lib/ports");
const dbm = require("@/lib/db");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// World creation is profile-only. The dedicated-server program is owned by
// Application Setup -> Server and is shared by every hosted World on this machine.
export async function POST(req) {
  try {
    const body = await req.json();
    const { display_name, ports, admin_password, owner_id, default_world_name } = body || {};
    const installDir = dbm.getSetting("applicationSetup:serverDir", null);
    const platform = dbm.getSetting("applicationSetup:serverPlatform", process.platform === "win32" ? "windows" : "linux");
    if (!installDir) {
      return NextResponse.json({
        ok: false,
        error: "Run Application Setup -> Server first. World profiles do not install their own dedicated-server copy.",
      }, { status: 409 });
    }
    if (ports) {
      const conflicts = conflictsInRegistry(ports);
      if (conflicts.length) {
        return NextResponse.json({ ok: false, error: `Port conflict with ${conflicts[0].usedBy} (port ${conflicts[0].port})` }, { status: 400 });
      }
    }
    const world = prov.createProfile({
      display_name,
      install_dir: installDir,
      ports,
      admin_password,
      platform,
      owner_id,
      default_world_name,
    });
    return NextResponse.json({ ok: true, world });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}
