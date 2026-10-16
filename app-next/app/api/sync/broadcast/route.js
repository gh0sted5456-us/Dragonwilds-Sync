import { NextResponse } from "next/server";
const discovery = require("@/lib/sync/discovery");
const dbm = require("@/lib/db");
const ra = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Local administrator access required." }, { status: 403 });
  return NextResponse.json({ ok: true, enabled: dbm.getSetting("sync:lanDiscoveryEnabled", false) === true, ...discovery.status() });
}
export async function POST(req) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Local administrator access required." }, { status: 403 });
  try {
    const body = await req.json();
    const enabled = body.restore === true ? dbm.getSetting("sync:lanDiscoveryEnabled", false) === true : body.enabled === true;
    // Restore only a previously explicit choice; no game/server engine is started.
    if (!enabled) {
      dbm.setSetting("sync:lanDiscoveryEnabled", false);
      return NextResponse.json({ ok: true, enabled: false, ...discovery.stop() });
    }
    const status = await discovery.start(null);
    dbm.setSetting("sync:lanDiscoveryEnabled", true);
    return NextResponse.json({ ok: true, enabled: true, ...status });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}
