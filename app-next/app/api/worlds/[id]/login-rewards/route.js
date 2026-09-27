import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const rewards = require("@/lib/loginrewards");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Config for the DailyLoginRewards sync on one world: where the mod's players.json is
// (auto-detected under the UE4SS Mods folder, or a manual override / upload).
//
// GET  → current path state (override, auto-detected, found, count)
// PUT  → set/clear the manual path override   { path: "…" | "" }
// POST → upload a players.json's contents      { content: "{…}" }

function state(world) {
  const override = rewards.getPathOverride(world.world_id);
  const detected = world.install_dir ? rewards.autodetect(world.install_dir) : null;
  const read = rewards.readStreaks(world);
  return {
    override: override || null,
    detected: detected || null,
    resolved: read.path,
    source: read.source,
    found: read.found,
    count: read.players.length,
    error: read.error,
  };
}

export async function GET(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "players" });
  if (denied) return denied;
  return NextResponse.json({ ok: true, ...state(w) });
}

export async function PUT(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "players", action: "loginRewards.setPath", mutating: true });
  if (denied) return denied;
  const b = await req.json().catch(() => ({}));
  const p = typeof b.path === "string" ? b.path.trim() : "";
  // A non-empty path must actually parse, so a typo is caught here rather than silently
  // showing an empty leaderboard later.
  if (p) {
    try { rewards.parseFile(p); }
    catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
  }
  rewards.setPathOverride(w.world_id, p || null);
  return NextResponse.json({ ok: true, ...state(w) });
}

export async function POST(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "players", action: "loginRewards.upload", mutating: true });
  if (denied) return denied;
  const b = await req.json().catch(() => ({}));
  if (typeof b.content !== "string" || !b.content.trim())
    return NextResponse.json({ ok: false, error: "No file contents were provided." }, { status: 400 });
  try {
    const { count } = rewards.saveUpload(w.world_id, b.content);
    dbm.logEvent(w.world_id, "players", `Imported ${count} DailyLoginRewards streak(s) from an uploaded players.json`);
    return NextResponse.json({ ok: true, ...state(w) });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}
