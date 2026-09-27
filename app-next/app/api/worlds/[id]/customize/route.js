import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const ra = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "admin", action: "world.customize", mutating: true });
  if (denied) return denied;
  const { icon_data, banner_data, accent_color, display_name } = await req.json();
  const patch = {};
  // basic size guard: data URLs must be reasonable (<400KB) to keep the DB small
  const okSize = (s) => !s || s.length < 400_000;
  if (icon_data !== undefined) { if (!okSize(icon_data)) return NextResponse.json({ ok: false, error: "Icon too large (max ~300KB)" }, { status: 400 }); patch.icon_data = icon_data; }
  if (banner_data !== undefined) { if (!okSize(banner_data)) return NextResponse.json({ ok: false, error: "Banner too large (max ~300KB)" }, { status: 400 }); patch.banner_data = banner_data; }
  if (accent_color !== undefined) patch.accent_color = accent_color;
  if (display_name !== undefined && display_name.trim()) patch.display_name = display_name.trim();
  const updated = dbm.updateWorld(params.id, patch);
  return NextResponse.json({ ok: true, world: publicWorld(updated) });
}

function publicWorld(w) {
  const { admin_password, ...rest } = w;
  return rest;
}
