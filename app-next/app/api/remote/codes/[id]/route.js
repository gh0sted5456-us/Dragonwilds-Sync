import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

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

// Edit a code's scope/tabs/label or enable/disable it. Changes take effect on the guest's
// next heartbeat (~live): disabling makes resolveSession() return null, ending the session.
export async function PATCH(req, { params }) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  const cur = dbm.getRemoteCode(params.id);
  if (!cur) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  let b = {};
  try { b = await req.json(); } catch {}
  const patch = {};
  if ("label" in b) patch.label = (b.label || "").toString().trim() || null;
  if ("enabled" in b) patch.enabled = b.enabled ? 1 : 0;
  if ("tabs" in b) patch.tabs = JSON.stringify(ra.cleanTabs(b.tabs));
  if ("scope" in b) {
    const scope = b.scope === "world" ? "world" : "full";
    patch.scope = scope;
    if (scope === "world") {
      const wid = String(b.worldId ?? cur.world_id ?? "").trim();
      if (!wid || !dbm.getWorld(wid)) return NextResponse.json({ ok: false, error: "Pick a world for a per-world code." }, { status: 400 });
      patch.world_id = wid;
    } else {
      patch.world_id = null;
    }
  } else if ("worldId" in b && cur.scope === "world") {
    const wid = String(b.worldId || "").trim();
    if (!wid || !dbm.getWorld(wid)) return NextResponse.json({ ok: false, error: "Unknown world." }, { status: 400 });
    patch.world_id = wid;
  }
  const updated = dbm.updateRemoteCode(params.id, patch);
  return NextResponse.json({ ok: true, code: enrich(updated) });
}

// Delete a code — drops its live sessions but keeps the audit trail.
export async function DELETE(req, { params }) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  if (!dbm.getRemoteCode(params.id)) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  dbm.deleteRemoteCode(params.id);
  return NextResponse.json({ ok: true });
}
