import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const { loginStats } = require("@/lib/playerstats");
const rewards = require("@/lib/loginrewards");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// GET /api/worlds/[id]/player-stats — login-streak leaderboard derived from the
// world's stored join history (sessions table), with the DailyLoginRewards mod's own
// streak numbers merged in when its players.json is available (so the two stay in
// sync). Kept off the every-5s world GET so the Players tab only pays for it while open.
export async function GET(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "players" });
  if (denied) return denied;
  try {
    const stats = loginStats(w.world_id);
    const mod = rewards.readStreaks(w);

    // Index the mod's entries by normalized display name (the only key it has).
    const norm = (s) => String(s || "").trim().toLowerCase();
    const byName = new Map();
    for (const p of mod.players) byName.set(norm(p.name), p);

    const seen = new Set();
    for (const s of stats) {
      const hit = byName.get(norm(s.name));
      if (hit) {
        s.modStreak = hit.streak;
        s.lastReward = hit.lastReward;
        seen.add(norm(s.name));
      }
    }
    // Mod-file players with no session history in the app still deserve a row, else the
    // app would under-report who the mod is tracking.
    for (const p of mod.players) {
      if (seen.has(norm(p.name))) continue;
      stats.push({
        id: `mod:${p.name}`,
        name: p.name,
        firstSeen: null,
        lastSeen: p.lastReward,
        totalLogins: 0,
        currentStreak: 0,
        longestStreak: 0,
        modStreak: p.streak,
        lastReward: p.lastReward,
        modOnly: true,
      });
    }

    // Re-sort so mod streaks (when present) lead the board, else fall back to the app's
    // own current streak, then recency.
    stats.sort((a, b) =>
      (b.modStreak ?? -1) - (a.modStreak ?? -1) ||
      b.currentStreak - a.currentStreak ||
      b.longestStreak - a.longestStreak ||
      (b.lastSeen || 0) - (a.lastSeen || 0)
    );

    return NextResponse.json({
      ok: true,
      stats,
      modSync: { found: mod.found, path: mod.path, source: mod.source, error: mod.error, count: mod.players.length },
    });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 500 });
  }
}
