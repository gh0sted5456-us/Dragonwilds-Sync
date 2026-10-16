import { NextResponse } from "next/server";
const dbm = require("@/lib/db");
const migration = require("@/lib/server-migration");
const jobs = require("@/lib/jobs");
const ra = require("@/lib/remoteauth");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function authorize(req, id, mutating) {
  if (!dbm.getWorld(id)) return NextResponse.json({ ok: false, error: "Server profile not found." }, { status: 404 });
  return ra.guardResponse(req, { worldId: id, tab: "admin", action: "world.update", mutating });
}

export async function GET(req, { params }) {
  const denied = authorize(req, params.id, false);
  if (denied) return denied;
  try {
    const { previous, ...plan } = migration.plan(params.id);
    return NextResponse.json({ ok: true, plan });
  } catch (error) { return NextResponse.json({ ok: false, error: error.message }, { status: 409 }); }
}

export async function POST(req, { params }) {
  const denied = authorize(req, params.id, true);
  if (denied) return denied;
  let review;
  try {
    review = await req.json();
    const plan = migration.plan(params.id);
    if (!plan.canMigrate) throw new Error(plan.reason);
    if (review?.confirm !== true || review.source !== plan.source || review.destination !== plan.destination || review.coreDir !== plan.coreDir) throw new Error("Review and confirm the current source, destination and Core before migrating");
  } catch (error) { return NextResponse.json({ ok: false, error: error.message }, { status: 409 }); }
  const world = dbm.getWorld(params.id);
  const jobId = jobs.createJob({ type: "install", worldId: params.id, worldName: `${world.display_name} · profile migration` });
  // Set the global launch/update guard before yielding to any file I/O.
  jobs.setPhase(jobId, "copy", "Inspecting and migrating Server profile…");
  (async () => {
    try {
      const result = await migration.migrate(params.id, review, {
        jobId, onLog: (line) => jobs.logJob(jobId, line),
        onProgress: ({ percent, message }) => jobs.setProgress(jobId, percent, message),
      });
      jobs.logJob(jobId, `Recovery copy: ${result.recoverySource}. Server remains stopped; use Start when ready.`);
      jobs.finishJob(jobId, true, { worldId: params.id });
    } catch (error) {
      jobs.logJob(jobId, `ERROR: ${error.message}`);
      jobs.finishJob(jobId, false, { error: error.message });
    }
  })();
  return NextResponse.json({ ok: true, jobId });
}
