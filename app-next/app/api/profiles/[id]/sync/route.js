import { NextResponse } from "next/server";
const clientSync = require("@/lib/sync/client");
const dbm = require("@/lib/db");
const jobs = require("@/lib/jobs");
const { requestClientAdmission } = require("@/lib/sync/client-admission");
const { safeSyncText } = require("@/lib/sync-progress");
const remoteauth = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req, { params }) {
  if (!remoteauth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  const profile = dbm.getProfile(params.id);
  if (!profile) return NextResponse.json({ ok: false, error: "World profile not found" }, { status: 404 });
  const active = jobs.listJobs().find((job) => job.status === "running" && job.type === "sync" && job.worldId === params.id);
  if (active) return NextResponse.json({ ok: false, error: "This World is already synchronizing. Follow it in Downloads." }, { status: 409 });
  const jobId = jobs.createJob({ type: "sync", worldId: params.id, worldName: `${profile.display_name} · Mod sync` });
  const share = String(profile.server_world_id || "").startsWith("profile-");
  jobs.setSyncProgress(jobId, { phase: "auth", percent: null, share, message: "Connecting to the World…" });
  try {
    const result = await clientSync.synchronizeProfile(params.id, (event) => jobs.setSyncProgress(jobId, event), { requireOnline: true });
    if (!share) jobs.setSyncProgress(jobId, { phase: "ack", percent: 95, message: "Asking the host to approve your verified manifest…" });
    const admission = share ? null : await requestClientAdmission(params.id, { expectedRevision: result.manifest.revision });
    jobs.setSyncProgress(jobId, { phase: admission ? "ready" : "files-ready", percent: 100, approved: !!admission?.approved, share: !admission, message: admission ? "Verified and approved by the host." : "Shared files verified. Player shares do not issue server login approval." });
    jobs.finishJob(jobId, true, { worldId: params.id });
    return NextResponse.json({ ok: true, jobId, result, admission });
  } catch (e) {
    const error = ["EPERM", "EACCES", "EBUSY"].includes(e.code) ? "Windows is holding a profile file or folder. Close programs editing this profile and retry. See the log for the affected path." : e.name === "AbortError" ? "The World did not respond in time. Retry when the host is reachable." : safeSyncText(e.message);
    jobs.logJob(jobId, `ERROR: ${safeSyncText(e.message)}`);
    jobs.finishJob(jobId, false, { worldId: params.id, error });
    return NextResponse.json({ ok: false, error }, { status: 400 });
  }
}
