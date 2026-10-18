import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const sup = require("@/lib/supervisor");
const runtimes = require("@/lib/runtime-packages");
const jobs = require("@/lib/jobs");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods" });
  if (denied) return denied;
  return NextResponse.json({ ok: true, packages: runtimes.status(params.id) });
}

export async function POST(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "mods", action: "runtime.install", mutating: true });
  if (denied) return denied;
  if (sup.isRunning(w.world_id) || sup.pidAlive(w.process_id)) {
    return NextResponse.json({ ok: false, error: "Stop the world before replacing its UE4SS or RuneSchema runtime." }, { status: 409 });
  }
  const body = await req.json().catch(() => ({}));
  try {
    const kind = String(body.component || "").toLowerCase();
    const action = body.action || "install";
    if (!["install", "preview-clean", "clean", "restore-clean"].includes(action)) throw new Error("Unknown loader action.");
    if (action !== "install" && !ra.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required for runtime cleanup." }, { status: 403 });
    if (action === "preview-clean") return NextResponse.json({ ok: true, preview: await runtimes.cleanupPreview(params.id, kind) });
    const label = kind === "ue4ss-gamepass" ? "UE4SS · PC Game Pass" : kind === "ue4ss-steam" ? "UE4SS · Steam" : kind === "ue4ss-server" ? "UE4SS · Dedicated Server" : "RuneSchema";
    const active = jobs.listJobs().find((job) => job.status === "running" && job.worldId === params.id && job.worldName === `${w.display_name} · ${label}`);
    if (active) return NextResponse.json({ ok: true, jobId: active.id, alreadyRunning: true });
    const jobId = jobs.createJob({ type: "runtime", worldId: params.id, worldName: `${w.display_name} · ${label}` });
    setImmediate(async () => {
      try {
        const progress = ({ phase, percent, message, line }) => {
          jobs.setPhase(jobId, phase, message);
          jobs.setProgress(jobId, percent, message);
          if (line) jobs.logJob(jobId, line);
        };
        if (action === "clean") await runtimes.clean(params.id, kind, body.fingerprint, progress);
        else if (action === "restore-clean") await runtimes.restoreClean(params.id, kind, body.recoveryId, progress);
        else await runtimes.install(params.id, kind, body.zipPath, progress);
        dbm.logEvent(params.id, "mods", action === "clean" ? "Cleaned runtime outside Mods: " + label : action === "restore-clean" ? "Restored runtime cleanup: " + label : `Installed managed ${label} runtime package for host + client Sync`);
        jobs.finishJob(jobId, true, { worldId: params.id });
      } catch (error) {
        jobs.logJob(jobId, `ERROR: ${error.message}`);
        jobs.finishJob(jobId, false, { worldId: params.id, error: error.message });
      }
    });
    return NextResponse.json({ ok: true, jobId });
  } catch (e) {
    return NextResponse.json({ ok: false, error: e.message }, { status: 400 });
  }
}
