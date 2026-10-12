import { NextResponse } from "next/server";
const clientSync = require("@/lib/sync/client");
const dbm = require("@/lib/db");
const jobs = require("@/lib/jobs");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(_req, { params }) {
  const profile = dbm.getProfile(params.id);
  if (!profile) return NextResponse.json({ ok: false, error: "World profile not found" }, { status: 404 });
  const active = jobs.listJobs().find((job) => job.status === "running" && job.type === "sync" && job.worldId === params.id);
  if (active) return NextResponse.json({ ok: false, error: "This World is already synchronizing. Follow it in Downloads." }, { status: 409 });
  const jobId = jobs.createJob({ type: "sync", worldId: params.id, worldName: `${profile.display_name} · Mod sync` });
  try {
    const result = await clientSync.synchronizeProfile(params.id, ({ phase, percent, message, line }) => {
      jobs.setPhase(jobId, phase, message);
      jobs.setProgress(jobId, percent, message);
      if (line) jobs.logJob(jobId, line);
    });
    jobs.finishJob(jobId, true, { worldId: params.id });
    return NextResponse.json({ ok: true, jobId, result });
  } catch (e) {
    const error = e.name === "AbortError" ? "The World did not respond in time" : e.message;
    jobs.logJob(jobId, `ERROR: ${error}`);
    jobs.finishJob(jobId, false, { worldId: params.id, error });
    return NextResponse.json({ ok: false, error }, { status: 400 });
  }
}
