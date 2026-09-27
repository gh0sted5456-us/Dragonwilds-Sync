import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const prereqs = require("@/lib/prereqs");
const jobs = require("@/lib/jobs");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// GET  → current runtime status (Windows): { vcredist, directx, ok, hasBundled }.
// POST → kick off an elevated install job (downloads MS VC++ + runs the bundled UE
//        prereq installer), surfaced in the Downloads tray. Returns { jobId }.
export async function GET(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id });
  if (denied) return denied;
  const status = prereqs.check();
  return NextResponse.json({ ok: true, ...status, hasBundled: !!prereqs.bundledPrereqPath(w.install_dir), vcRedistUrl: prereqs.VC_REDIST_URL });
}

export async function POST(req, { params }) {
  const w = dbm.getWorld(params.id);
  if (!w) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "overview", action: "prereqs.install", mutating: true });
  if (denied) return denied;
  if (process.platform !== "win32") {
    return NextResponse.json({ ok: false, error: "Prerequisites are only needed on Windows." }, { status: 400 });
  }
  const jobId = jobs.createJob({ type: "redist", worldId: w.world_id, worldName: w.display_name });
  jobs.setPhase(jobId, "redist", "Preparing…");
  // Fire and forget: the job streams progress; the client watches the Downloads tray.
  (async () => {
    try {
      const r = await prereqs.installPrereqs(w.install_dir, {
        onLog: (l) => jobs.logJob(jobId, l),
        onProgress: (phase, pct) => {
          jobs.setPhase(jobId, "redist", phase === "download" ? "Downloading runtime…" : "Installing runtime…");
          if (pct != null) jobs.setProgress(jobId, pct);
        },
      });
      jobs.finishJob(jobId, r.ok, { error: r.ok ? null : "Some runtimes still appear missing — a reboot may be needed.", worldId: w.world_id });
      dbm.logEvent(w.world_id, "settings", r.ok ? "Installed Windows runtime prerequisites" : "Ran prerequisite installer — some runtimes still missing");
    } catch (e) {
      jobs.logJob(jobId, `Error: ${e.message}`);
      jobs.finishJob(jobId, false, { error: e.message, worldId: w.world_id });
    }
  })();
  return NextResponse.json({ ok: true, jobId });
}
