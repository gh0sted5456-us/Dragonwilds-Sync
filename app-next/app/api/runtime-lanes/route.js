import { NextResponse } from "next/server";
const lanes = require("@/lib/runtime-lanes");
const jobs = require("@/lib/jobs");
const remoteauth = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req) {
  if (!remoteauth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  try {
    const platform = new URL(req.url).searchParams.get("platform");
    return NextResponse.json({ ok: true, lane: lanes.status(platform) });
  } catch (error) { return NextResponse.json({ ok: false, error: error.message }, { status: 400 }); }
}
export async function POST(req) {
  if (!remoteauth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  try {
    const { platform, component, zipPath, action = "install", fingerprint, recoveryId } = await req.json();
    lanes.packageRoot(platform, component);
    if (action === "preview-clean") return NextResponse.json({ ok: true, preview: await lanes.cleanupPreview(platform, component) });
    if (!["install", "clean", "restore-clean"].includes(action)) throw new Error("Unknown loader action.");
    const worldId = "runtime-lane:" + platform;
    const active = jobs.listJobs().find((job) => job.status === "running" && job.worldId === worldId);
    if (active) return NextResponse.json({ ok: true, jobId: active.id, alreadyRunning: true });
    const jobId = jobs.createJob({ type: "runtime", worldId, worldName: "Loader Setup · " + lanes.status(platform).label });
    setImmediate(async () => {
      try {
        const progress = ({ phase, percent, message, line }) => {
          jobs.setPhase(jobId, phase, message); jobs.setProgress(jobId, percent, message);
          if (line) jobs.logJob(jobId, line);
        };
        if (action === "clean") await lanes.clean(platform, component, fingerprint, progress);
        else if (action === "restore-clean") await lanes.restoreClean(platform, component, recoveryId, progress);
        else await lanes.install(platform, component, zipPath, progress);
        jobs.finishJob(jobId, true);
      } catch (error) { jobs.logJob(jobId, "ERROR: " + error.message); jobs.finishJob(jobId, false, { error: error.message }); }
    });
    return NextResponse.json({ ok: true, jobId });
  } catch (error) { return NextResponse.json({ ok: false, error: error.message }, { status: 400 }); }
}
