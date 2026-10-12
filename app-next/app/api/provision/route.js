import { NextResponse } from "next/server";
const crypto = require("crypto");
const prov = require("@/lib/provision");
const { conflictsInRegistry } = require("@/lib/ports");
const dbm = require("@/lib/db");
const detect = require("@/lib/detect");
const forks = require("@/lib/server-forks");
const jobs = require("@/lib/jobs");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// World creation is profile-only. The dedicated-server program is owned by
// Application Setup -> Server and is shared by every hosted World on this machine.
export async function POST(req) {
  if (!ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Admin access required." }, { status: 403 });
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
    const effectiveOwnerId = String(owner_id || dbm.getSetting("applicationSetup:ownerId", "") || "").trim();
    if (!effectiveOwnerId) throw new Error("Set a default Owner ID in Application Setup → Dedicated Server, or enter a profile override.");
    const source = detect.inspect(installDir);
    if (!source.valid) throw new Error(source.reason || "The shared Server lane is not ready.");
    if (jobs.listJobs().some((job) => job.status === "running" && job.worldName === "Application Setup · Server")) {
      return NextResponse.json({ ok: false, error: "Wait for the shared SteamCMD setup/update to finish before creating a Server profile." }, { status: 409 });
    }
    const worldId = crypto.randomUUID();
    forks.forkPath(installDir, worldId); // validate the configured destination before accepting the job
    const jobId = jobs.createJob({ type: "install", worldId, worldName: display_name || "New Server profile" });
    (async () => {
      try {
        jobs.setPhase(jobId, "copy", "Forking private server files…");
        const fork = await forks.forkInstall(installDir, worldId, { onLog: (line) => jobs.logJob(jobId, line) });
        const world = prov.createProfile({
          world_id: worldId,
          display_name,
          install_dir: fork.installDir,
          ports,
          admin_password,
          platform: fork.platform || platform,
          owner_id: effectiveOwnerId,
          default_world_name,
        });
        jobs.logJob(jobId, `Created ${world.display_name} with its own server folder.`);
        jobs.finishJob(jobId, true, { worldId });
      } catch (error) {
        jobs.logJob(jobId, `ERROR: ${error.message}`);
        jobs.finishJob(jobId, false, { error: error.message });
      }
    })();
    return NextResponse.json({ ok: true, jobId, worldId });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}
