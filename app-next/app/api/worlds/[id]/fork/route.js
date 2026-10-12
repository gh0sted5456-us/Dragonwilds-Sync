import { NextResponse } from "next/server";
const path = require("path");
const dbm = require("@/lib/db");
const sup = require("@/lib/supervisor");
const active = require("@/lib/active-server-profile");
const forks = require("@/lib/server-forks");
const jobs = require("@/lib/jobs");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  const world = dbm.getWorld(params.id);
  if (!world) return NextResponse.json({ ok: false, error: "Server profile not found." }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "admin", action: "world.update", mutating: true });
  if (denied) return denied;
  const template = dbm.getSetting("applicationSetup:serverDir", null);
  if (!template || path.resolve(world.install_dir).toLowerCase() !== path.resolve(template).toLowerCase()) {
    return NextResponse.json({ ok: false, error: "This Server profile already has its own folder." }, { status: 409 });
  }
  if (active.readActiveId() !== world.world_id) {
    return NextResponse.json({ ok: false, error: "Activate this Server profile before copying the shared folder's current save." }, { status: 409 });
  }
  if (dbm.listWorlds().some((w) => sup.isRunning(w.world_id) || sup.pidAlive(w.process_id))) {
    return NextResponse.json({ ok: false, error: "Stop all hosted Servers before forking a shared installation." }, { status: 409 });
  }
  if (jobs.listJobs().some((job) => job.status === "running" && ["install", "update"].includes(job.type))) {
    return NextResponse.json({ ok: false, error: "Wait for the current Server file job to finish before forking." }, { status: 409 });
  }
  try { forks.forkPath(template, world.world_id); }
  catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }

  const jobId = jobs.createJob({ type: "install", worldId: world.world_id, worldName: `${world.display_name} · private files` });
  (async () => {
    try {
      jobs.setPhase(jobId, "copy", "Copying this Server's current files and save…");
      const fork = await forks.forkInstall(template, world.world_id, { includeSaved: true, onLog: (line) => jobs.logJob(jobId, line) });
      // The old shared folder is preserved. Only this profile changes paths.
      dbm.updateWorld(world.world_id, { install_dir: fork.installDir, build_id: fork.buildId || world.build_id });
      const legacyRuntime = dbm.getSetting("applicationSetup:activeServerRuntimeFiles", { files: [] });
      dbm.setSetting(`serverRuntimeFiles:${world.world_id}`, legacyRuntime);
      jobs.logJob(jobId, "Server now owns its private installation. Original shared files were not removed.");
      jobs.finishJob(jobId, true, { worldId: world.world_id });
    } catch (error) {
      jobs.logJob(jobId, `ERROR: ${error.message}`);
      jobs.finishJob(jobId, false, { error: error.message });
    }
  })();
  return NextResponse.json({ ok: true, jobId });
}
