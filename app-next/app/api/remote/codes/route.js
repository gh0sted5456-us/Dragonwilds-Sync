import { NextResponse } from "next/server";
const crypto = require("crypto");
const dbm = require("@/lib/db");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Admin-only: the desktop app manages codes. Guests can never reach this.
function enrich(c) {
  const world = c.world_id ? dbm.getWorld(c.world_id) : null;
  return {
    id: c.id, code: c.code, label: c.label || "", scope: c.scope,
    worldId: c.world_id || null, worldName: world ? world.display_name : null,
    tabs: ra.tabsOf(c), enabled: !!c.enabled,
    createdAt: c.created_at, lastUsedAt: c.last_used_at || null,
    activeSessions: dbm.countActiveSessions(c.id, Date.now() - ra.ACTIVE_WINDOW_MS),
  };
}

export async function GET(req) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  return NextResponse.json({ ok: true, codes: dbm.listRemoteCodes().map(enrich) });
}

export async function POST(req) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  let b = {};
  try { b = await req.json(); } catch {}
  const scope = b.scope === "world" ? "world" : "full";
  let worldId = null;
  if (scope === "world") {
    worldId = String(b.worldId || "").trim();
    if (!worldId || !dbm.getWorld(worldId)) return NextResponse.json({ ok: false, error: "Pick a world for a per-world code." }, { status: 400 });
  }
  const tabs = Array.isArray(b.tabs) ? ra.cleanTabs(b.tabs) : ra.DEFAULT_TABS;
  const now = Date.now();
  const code = dbm.insertRemoteCode({
    id: crypto.randomUUID(), code: ra.generateCode(),
    label: (b.label || "").toString().trim() || null,
    scope, world_id: worldId, tabs: JSON.stringify(tabs),
    enabled: 1, created_at: now,
  });
  return NextResponse.json({ ok: true, code: enrich(code) });
}
