import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const remoteauth = require("@/lib/remoteauth");
const refresh = require("@/lib/sync/profile-refresh");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req) {
  if (!remoteauth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  const activeId = dbm.getActiveLauncherProfileId();
  const allowed = new Set(dbm.listLauncherProfileWorldIds(activeId, "player"));
  const queue = dbm.listProfiles().filter((profile) => allowed.has(profile.profile_id));
  const results = [];
  let cursor = 0;
  const worker = async () => {
    while (cursor < queue.length) {
      const profile = queue[cursor++];
      try { results.push(await refresh.refreshProfile(profile)); }
      catch (error) { results.push({ profileId: profile.profile_id, error: error?.name === "AbortError" ? "World did not respond in time" : error.message }); }
    }
  };
  await Promise.all(Array.from({ length: Math.min(4, Math.max(1, queue.length)) }, worker));
  return NextResponse.json({
    ok: true,
    checked: results.filter((result) => !result.skipped).length,
    updates: results.filter((result) => result.updateAvailable).length,
    changed: results.filter((result) => result.changed).length,
    skipped: results.filter((result) => result.skipped).length,
    errors: results.filter((result) => result.error).length,
    results,
  });
}
