import { NextResponse } from "next/server";
const mods = require("@/lib/mods");
const ra = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Set (or clear, with an empty/null path) the machine-wide Steam library override
// used to locate Workshop content when Steam isn't on the default C: location.
export async function POST(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods", action: "mods.steamLibrary", mutating: true });
  if (denied) return denied;
  try {
    const { path } = await req.json();
    mods.setSteamLibraryOverride(path);
    return NextResponse.json({ ok: true, ...mods.status(params.id) });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}
