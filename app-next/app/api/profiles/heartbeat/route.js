import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const heartbeat = require("@/lib/sync/heartbeat");
const refresh = require("@/lib/sync/profile-refresh");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST() {
  const activeId = dbm.getActiveLauncherProfileId();
  const allowed = new Set(dbm.listLauncherProfileWorldIds(activeId, "player"));
  const profiles = dbm.listProfiles().filter((profile) => allowed.has(profile.profile_id));
  const statuses = await Promise.all(profiles.map(async (profile) => {
    const connection = JSON.parse(profile.connection_json || "{}");
    if (connection.localWorld) return { profileId: profile.profile_id, state: "local", skipped: true };
    const status = await heartbeat.probe({ ...connection, worldId: connection.worldId || profile.server_world_id });
    let update = null;
    if (status.online && status.revision && String(status.revision) !== String(profile.last_manifest_revision || "")) {
      try { update = await refresh.refreshProfile(profile); } catch { /* heartbeat remains useful even when the full manifest fails */ }
    }
    const latest = dbm.getProfile(profile.profile_id) || profile;
    const latestConnection = JSON.parse(latest.connection_json || "{}");
    dbm.upsertProfile({ profile_id: profile.profile_id, connection: { ...latestConnection, heartbeat: status } });
    return { profileId: profile.profile_id, ...status, updateAvailable: update?.updateAvailable ?? latestConnection.manifestUpdate?.available ?? false };
  }));
  return NextResponse.json({ ok: true, intervalMs: 10 * 60 * 1000, statuses });
}
