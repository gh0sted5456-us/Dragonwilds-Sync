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
    const label = kind === "ue4ss-gamepass" ? "UE4SS · PC Game Pass" : kind === "ue4ss-steam" ? "UE4SS · Steam" : kind === "ue4ss-server" ? "UE4SS · Dedicated Server" : "RuneSchema";
    const active = jobs.listJobs().find((job) => job.status === "running" && job.worldId === params.id && job.worldName === `${w.display_name} · ${label}`);
    if (active) return NextResponse.json({ ok: true, jobId: active.id, alreadyRunning: true });
    const jobId = jobs.createJob({ type: "runtime", worldId: params.id, worldName: `${w.display_name} · ${label}` });
    setImmediate(async () => {
      try {
        await runtimes.install(params.id, kind, body.zipPath, ({ phase, percent, message, line }) => {
          jobs.setPhase(jobId, phase, message);
          jobs.setProgress(jobId, percent, message);
          if (line) jobs.logJob(jobId, line);
        });
        dbm.logEvent(params.id, "mods", `Installed managed ${label} runtime package for host + client Sync`);
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
